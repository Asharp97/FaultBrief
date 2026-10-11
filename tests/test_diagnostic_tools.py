import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.diagnostics.bindings import SECRET_REF, DiagnosticError, Registry, resolve_scope
from backend.app.diagnostics.cli import connect
from backend.app.diagnostics.client import DiagnosticTools
from backend.app.diagnostics.config import DiagnosticSettings
from backend.app.diagnostics.contracts import Scope
from backend.app.domain import IntegrationKind, MembershipRole
from backend.app.models import Customer, Integration, Membership, User, Workspace
from demo.app.config import DemoSettings
from demo.app.main import create_app as demo_app

TOKEN = "synthetic-diagnostic-" + "d" * 32


def response(data, status=200, headers=None):
    return httpx2.Response(
        status,
        headers={"Content-Type": "application/json", **(headers or {})},
        stream=httpx2.ByteStream(json.dumps(data).encode()),
    )


@pytest.fixture
def scope():
    return Scope(
        workspace_id=uuid4(),
        customer_id=uuid4(),
        integration_id=uuid4(),
        source_customer_id=uuid4(),
    )


def settings(tmp_path, **overrides):
    return DiagnosticSettings(
        _env_file=None, demo_token=TOKEN, bindings_path=tmp_path / "bindings.json", **overrides
    )


def source_data(scope):
    now = datetime.now(UTC).isoformat()
    member_id, request_id = str(uuid4()), str(uuid4())
    job = {
        "id": str(uuid4()),
        "customer_id": str(scope.source_customer_id),
        "member_id": member_id,
        "report_id": str(uuid4()),
        "request_id": request_id,
        "state": "failed",
        "error_code": "STORAGE_WRITE_FAILED",
        "created_at": now,
        "started_at": now,
        "finished_at": now,
    }
    log = {
        "id": str(uuid4()),
        "customer_id": str(scope.source_customer_id),
        "member_id": member_id,
        "request_id": request_id,
        "event": "export_failed",
        "status_code": 500,
        "message_redacted": "Artifact write rejected",
        "observed_at": now,
    }
    return {
        "features": {
            "id": str(scope.source_customer_id),
            "name": "Synthetic account",
            "external_id": "source-account",
            "exports_enabled": True,
            "config_version": 1,
            "updated_at": now,
        },
        "permissions": {
            "items": [
                {
                    "id": member_id,
                    "customer_id": str(scope.source_customer_id),
                    "name": "Jamie",
                    "role": "analyst",
                    "permissions": ["exports.create"],
                }
            ]
        },
        "jobs": {"items": [job], "limit": 20, "offset": 0},
        "logs": {"items": [log], "limit": 20, "offset": 0, "coverage": "full"},
    }


def transport(data, seen=None):
    def handle(request):
        if seen is not None:
            seen.append(request)
        kind = "features" if request.url.path.count("/") == 3 else request.url.path.split("/")[4]
        kind = {"members": "permissions"}.get(kind, kind)
        payload = data[kind]
        if kind in {"jobs", "logs"}:
            if kind == "jobs" and request.url.path.count("/") == 5:
                payload = payload["items"][0]
            else:
                payload = {**payload, "limit": int(request.url.params["limit"])}
        return response(payload)

    return httpx2.MockTransport(handle)


def test_tools_are_read_only_and_bound_without_any_model(scope, tmp_path):
    data, seen = source_data(scope), []
    tools = DiagnosticTools(scope, settings(tmp_path), transport=transport(data, seen))
    for tool in ("permissions", "features", "jobs", "logs", "runbooks"):
        result = tools.run(tool)
        assert result.state == "completed", result.model_dump_json()
        assert TOKEN not in result.model_dump_json() and "Jamie" not in result.model_dump_json()
    assert len(seen) == 4
    assert all(
        item.method == "GET" and str(scope.source_customer_id) in item.url.path for item in seen
    )
    assert all(item.headers["authorization"] == f"Bearer {TOKEN}" for item in seen)
    assert not any("/lab/" in item.url.path for item in seen)


@pytest.mark.parametrize(
    "tool,args",
    [
        ("features", {"url": "https://untrusted.invalid"}),
        ("permissions", {"member_id": "../other"}),
        ("jobs", {"limit": 51}),
        ("logs", {"limit": "20"}),
        ("runbooks", {"runbook_id": "../../training/data/private/answers"}),
        ("features", {"customer_id": str(uuid4())}),
    ],
)
def test_invalid_arguments_never_contact_the_source(scope, tmp_path, tool, args):
    seen = []
    result = DiagnosticTools(
        scope, settings(tmp_path), transport=transport(source_data(scope), seen)
    ).run(tool, args)
    assert result.code == "invalid_arguments" and seen == []


@pytest.mark.parametrize("tool", ["features", "permissions", "jobs", "logs"])
def test_cross_customer_source_responses_are_rejected(scope, tmp_path, tool):
    data = source_data(scope)
    target = data[tool] if tool == "features" else data[tool]["items"][0]
    target["id" if tool == "features" else "customer_id"] = str(uuid4())
    result = DiagnosticTools(scope, settings(tmp_path), transport=transport(data)).run(tool)
    assert result.code == "source_scope_mismatch" and result.data == {}


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "connector_unauthorized"),
        (403, "connector_forbidden"),
        (404, "source_not_found"),
        (429, "connector_rate_limited"),
        (503, "connector_unavailable"),
        (302, "connector_unavailable"),
    ],
)
def test_source_failures_do_not_leak_bodies_or_follow_redirects(scope, tmp_path, status, code):
    seen = []

    def handler(request):
        seen.append(request)
        return response({"private_error": TOKEN}, status, {"Location": "https://untrusted.invalid"})

    result = DiagnosticTools(
        scope, settings(tmp_path), transport=httpx2.MockTransport(handler)
    ).run("features")
    assert result.code == code and TOKEN not in result.model_dump_json() and len(seen) == 1


def test_timeout_and_deadline_fail_safely(scope, tmp_path):
    def timeout(request):
        raise httpx2.ReadTimeout(TOKEN, request=request)

    tools = DiagnosticTools(scope, settings(tmp_path), transport=httpx2.MockTransport(timeout))
    assert tools.run("features").code == "connector_timeout"
    tools.deadline = 0
    assert tools.run("features").code == "diagnostic_deadline_exceeded"


def test_request_and_byte_limits_are_enforced(scope, tmp_path):
    tools = DiagnosticTools(
        scope, settings(tmp_path, max_requests=1), transport=transport(source_data(scope))
    )
    assert tools.run("features").state == "completed"
    assert tools.run("features").code == "request_budget_exceeded"
    tools = DiagnosticTools(
        scope,
        settings(tmp_path, max_response_bytes=1024),
        transport=httpx2.MockTransport(lambda _: response({"large": "x" * 2000})),
    )
    assert tools.run("features").code == "source_response_too_large"


def test_record_limits_correlation_and_redaction(scope, tmp_path):
    data, seen = source_data(scope), []
    log = data["logs"]["items"][0]
    log["message_redacted"] = f"password=private Bearer {TOKEN} plain {TOKEN} jamie@example.invalid"
    tools = DiagnosticTools(
        scope, settings(tmp_path, max_records=1), transport=transport(data, seen)
    )
    result = tools.run("logs", {"request_id": log["request_id"], "limit": 50})
    assert result.state == "completed" and result.truncated
    assert seen[0].url.params["limit"] == "1"
    assert "private" not in result.model_dump_json() and TOKEN not in result.model_dump_json()
    assert "jamie@example.invalid" not in result.model_dump_json()
    assert tools.run("logs", {"request_id": str(uuid4())}).code == "source_scope_mismatch"
    assert tools.run("jobs", {"job_id": str(uuid4())}).code == "source_scope_mismatch"
    assert tools.run("permissions", {"member_id": str(uuid4())}).code == "member_not_found"


def test_malformed_unexpected_and_missing_sources(scope, tmp_path):
    data = source_data(scope)
    data["features"]["fault_mode"] = "private-answer"
    assert (
        DiagnosticTools(scope, settings(tmp_path), transport=transport(data)).run("features").code
        == "invalid_source_response"
    )
    tools = DiagnosticTools(scope, settings(tmp_path, runbooks_path=tmp_path / "absent.json"))
    assert tools.run("runbooks").code == "runbooks_unavailable"
    tools = DiagnosticTools(scope, DiagnosticSettings(_env_file=None, demo_token=None))
    assert tools.run("features").code == "connector_not_configured"


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.invalid",
        "https://user:secret@remote.invalid",
        "https://remote.invalid/path",
        "file:///etc/passwd",
    ],
)
def test_untrusted_connector_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        DiagnosticSettings(_env_file=None, demo_url=url)
    with pytest.raises(ValidationError):
        DiagnosticSettings(
            _env_file=None, environment="production", demo_url="http://127.0.0.1:8001"
        )


def test_scope_resolution_requires_approved_active_integration(db_session, tmp_path):
    workspace = Workspace(name="Approved company")
    db_session.add(workspace)
    db_session.flush()
    customer = Customer(workspace_id=workspace.id, name="Customer", external_id="same-guessed-id")
    integration = Integration(
        workspace_id=workspace.id,
        name="Ledger",
        kind=IntegrationKind.DEMO,
        enabled=True,
        secret_ref=SECRET_REF,
    )
    db_session.add_all([customer, integration])
    db_session.flush()
    config = settings(tmp_path)
    scope = Scope(
        workspace_id=workspace.id,
        customer_id=customer.id,
        integration_id=integration.id,
        source_customer_id=uuid4(),
    )
    with pytest.raises(DiagnosticError, match="customer_not_connected"):
        resolve_scope(db_session, workspace.id, customer.id, config.bindings_path)
    Registry(bindings=[scope]).save(config.bindings_path)
    assert resolve_scope(db_session, workspace.id, customer.id, config.bindings_path) == scope
    with pytest.raises(DiagnosticError, match="customer_not_found"):
        resolve_scope(db_session, uuid4(), customer.id, config.bindings_path)
    integration.enabled = False
    db_session.flush()
    with pytest.raises(DiagnosticError, match="integration_not_connected"):
        resolve_scope(db_session, workspace.id, customer.id, config.bindings_path)


@pytest.mark.parametrize(
    "scenario", ["healthy", "permission_removed", "feature_disabled", "job_failed", "ambiguous"]
)
def test_real_demo_scenarios_are_observable_without_operator_access(db_session, tmp_path, scenario):
    app = demo_app(
        DemoSettings(
            _env_file=None,
            environment="test",
            database_path=tmp_path / "demo.sqlite3",
            diagnostic_token=TOKEN,
            operator_token="synthetic-operator-" + "o" * 32,
            app_token="synthetic-app-" + "a" * 32,
        )
    )
    with TestClient(app) as demo:
        case = app.state.store.create_run(scenario)
        workspace = Workspace(name="Synthetic company")
        user = User(auth_issuer="https://auth.invalid", auth_subject=str(uuid4()))
        db_session.add_all([workspace, user])
        db_session.flush()
        db_session.add(
            Membership(workspace_id=workspace.id, user_id=user.id, role=MembershipRole.OWNER)
        )
        db_session.flush()

        def handle(request):
            source = demo.get(
                request.url.raw_path.decode(),
                headers={"Authorization": request.headers["Authorization"]},
            )
            return response(source.json(), source.status_code)

        config = settings(tmp_path)
        source_transport = httpx2.MockTransport(handle)
        scope = connect(
            db_session,
            config,
            workspace.id,
            user.id,
            case["customer_id"],
            transport=source_transport,
        )
        approved = resolve_scope(db_session, workspace.id, scope.customer_id, config.bindings_path)
        tools = DiagnosticTools(approved, config, transport=source_transport)
        results = {
            tool: tools.run(tool)
            for tool in ["permissions", "features", "jobs", "logs", "runbooks"]
        }
        assert all(result.state == "completed" for result in results.values())
        assert results["features"].data["exports_enabled"] is (scenario != "feature_disabled")
        assert results["logs"].data["coverage"] == (
            "partial" if scenario == "ambiguous" else "full"
        )
        # Even a guessed source ID is not a substitute for the approved server mapping.
        guessed = Customer(workspace_id=workspace.id, name="Guessed", external_id="guessed-source")
        db_session.add(guessed)
        db_session.flush()
        with pytest.raises(DiagnosticError, match="customer_not_connected"):
            resolve_scope(db_session, workspace.id, guessed.id, config.bindings_path)


def test_registry_rejects_duplicate_source_assignments(scope):
    other = scope.model_copy(update={"workspace_id": uuid4(), "customer_id": uuid4()})
    with pytest.raises(ValidationError):
        Registry(bindings=[scope, other])
