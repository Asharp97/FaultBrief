import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.database import get_session
from backend.app.diagnostics.cli import connect
from backend.app.diagnostics.config import DiagnosticSettings
from backend.app.domain import InvestigationState, JobState
from backend.app.investigations.config import InvestigationSettings
from backend.app.investigations.worker import Worker
from backend.app.main import create_app
from backend.app.models import Evidence, Investigation, Job, Membership, Report, ToolCall
from backend.app.schemas import ReportDraft
from backend.app.services import save_report
from demo.app.config import DemoSettings
from demo.app.main import create_app as demo_app

TOKEN = "synthetic-diagnostic-" + "d" * 32


def response(data):
    return httpx2.Response(
        200,
        headers={"Content-Type": "application/json"},
        stream=httpx2.ByteStream(json.dumps(data).encode()),
    )


@pytest.fixture
def harness(db_session, postgres_engine, tmp_path):
    issuer = "https://auth.example.invalid"
    app = create_app(
        Settings(_env_file=None, auth_url=f"{issuer}/neondb/auth", jwks_url=f"{issuer}/jwks"),
        engine=postgres_engine,
    )

    def session_override():
        yield db_session

    app.dependency_overrides[get_session] = session_override
    key = Ed25519PrivateKey.generate()
    app.state.token_verifier.jwks.get_signing_key_from_jwt = lambda _: SimpleNamespace(
        key=key.public_key(), algorithm_name="EdDSA"
    )

    def actor(subject):
        now = datetime.now(UTC)
        token = jwt.encode(
            {"iss": issuer, "sub": subject, "iat": now, "exp": now + timedelta(minutes=5)},
            key,
            algorithm="EdDSA",
            headers={"kid": "synthetic-key"},
        )
        return TestClient(app, headers={"Authorization": f"Bearer {token}"})

    owner = actor("owner")
    workspace = owner.post("/v1/workspaces", json={"name": "Investigation lab"}).json()["id"]
    owner_id = owner.get("/v1/me").json()["id"]
    source = demo_app(
        DemoSettings(
            _env_file=None,
            environment="test",
            database_path=tmp_path / "ledger.sqlite3",
            diagnostic_token=TOKEN,
            operator_token="synthetic-operator-" + "o" * 32,
            app_token="synthetic-app-" + "a" * 32,
        )
    )
    seen = []
    with TestClient(source) as demo:

        def handle(request):
            seen.append(request)
            upstream = demo.get(
                request.url.raw_path.decode(),
                headers={"Authorization": request.headers["Authorization"]},
            )
            return httpx2.Response(
                upstream.status_code,
                headers={"Content-Type": "application/json"},
                stream=httpx2.ByteStream(upstream.content),
            )

        transport = httpx2.MockTransport(handle)
        config = DiagnosticSettings(
            _env_file=None, demo_token=TOKEN, bindings_path=tmp_path / "bindings.json"
        )

        @contextmanager
        def session_factory():
            try:
                yield db_session
            except Exception:
                db_session.rollback()
                raise

        def case(scenario, **context):
            record = source.state.store.create_run(scenario)
            binding = connect(
                db_session,
                config,
                UUID(workspace),
                UUID(owner_id),
                UUID(record["customer_id"]),
                transport=transport,
            )
            ticket = owner.post(
                f"/v1/workspaces/{workspace}/investigations",
                json={
                    "customer_id": str(binding.customer_id),
                    "question": "Why did this customer's revenue export fail?",
                    "context": {"member_id": record["member_id"], **context},
                },
            )
            assert ticket.status_code == 201, ticket.text
            return ticket.json()["id"], record

        def worker(model_transport=None, enabled=False):
            return Worker(
                postgres_engine,
                InvestigationSettings(
                    _env_file=None,
                    model_provider="openai-compatible" if enabled else None,
                    model_name="synthetic-explainer" if enabled else None,
                    ai_provider_api_key="synthetic-model-key" if enabled else None,
                ),
                config,
                tool_transport=transport,
                model_transport=model_transport,
                session_factory=session_factory,
            )

        yield SimpleNamespace(
            owner=owner,
            workspace=workspace,
            case=case,
            worker=worker,
            actor=actor,
            seen=seen,
            db=db_session,
        )


@pytest.mark.parametrize(
    "scenario,expected,root",
    [
        ("permission_removed", "completed", "lacks exports.create"),
        ("feature_disabled", "completed", "Exports are disabled"),
        ("job_failed", "completed", "storage rejected"),
        ("healthy", "completed", None),
        ("ambiguous", "inconclusive", None),
    ],
)
def test_ticket_to_report_uses_real_scoped_demo_evidence(harness, scenario, expected, root):
    iid, _ = harness.case(scenario)
    assert harness.worker().run_once() == expected
    base = f"/v1/workspaces/{harness.workspace}/investigations/{iid}"
    report = harness.owner.get(base + "/report")
    assert report.status_code == 200, report.text
    data = report.json()
    assert data["observed_facts"] and data["next_steps"] and data["explanation_source"] == "rules"
    assert root in data["root_cause"] if root else data["root_cause"] is None
    evidence = harness.owner.get(base + "/evidence").json()["items"]
    assert {c["evidence_id"] for c in data["citations"]}.issubset({e["id"] for e in evidence})
    assert all(
        e["workspace_id"] == harness.workspace and e["investigation_id"] == iid for e in evidence
    )
    assert harness.owner.get(base + "/jobs").json()["items"][0]["state"] == "completed"
    assert harness.owner.get(base).json()["state"] == expected
    assert len(harness.owner.get(base + "/tool-calls").json()["items"]) == 5
    assert all(request.method == "GET" for request in harness.seen)
    assert TOKEN not in report.text and "fault_mode" not in report.text
    stranger = harness.actor("stranger")
    assert stranger.get(base + "/report").status_code == 404
    assert stranger.get(base + "/evidence").status_code == 404
    if scenario == "ambiguous":
        assert any("symptom" in item for item in data["limitations"])


def model_response(request, mutation=None):
    payload = json.loads(request.content)
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["store"] is False and "synthetic-model-key" not in request.content.decode()
    context = json.loads(payload["messages"][1]["content"])
    result = context["baseline"]
    result["summary"] = "AI explanation: " + result["summary"]
    if mutation:
        mutation(result)
    return response(
        {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
    )


def test_model_explains_locked_findings_and_real_citations(harness):
    iid, _ = harness.case("feature_disabled")
    model = httpx2.MockTransport(model_response)
    assert harness.worker(model, True).run_once() == "completed"
    report = harness.owner.get(
        f"/v1/workspaces/{harness.workspace}/investigations/{iid}/report"
    ).json()
    assert report["explanation_source"] == "model" and report["summary"].startswith(
        "AI explanation"
    )
    assert report["root_cause"] == "Exports are disabled for this customer."


@pytest.mark.parametrize("bad", ["cause", "fact", "citation", "quote", "confidence"])
def test_unsupported_model_claims_fall_back_to_verified_rules(harness, bad):
    iid, _ = harness.case("feature_disabled")

    def mutate(result):
        if bad == "cause":
            result["root_cause"] = "A fabricated database outage."
        if bad == "fact":
            result["observed_facts"] = ["The agent reset the account."]
        if bad == "citation":
            result["citations"][0]["evidence_id"] = str(uuid4())
        if bad == "quote":
            result["citations"][0]["quote"] = "A fabricated quote."
        if bad == "confidence":
            result["confidence"] = 1.0

    model = httpx2.MockTransport(lambda request: model_response(request, mutate))
    assert harness.worker(model, True).run_once() == "completed"
    report = harness.owner.get(
        f"/v1/workspaces/{harness.workspace}/investigations/{iid}/report"
    ).json()
    assert report["explanation_source"] == "rules_fallback"
    assert report["root_cause"] == "Exports are disabled for this customer."
    assert not any("fabricated" in value.lower() for value in report["observed_facts"])


def test_model_timeout_keeps_a_usable_report(harness):
    iid, _ = harness.case("permission_removed")

    def timeout(request):
        raise httpx2.ReadTimeout("private provider details", request=request)

    assert harness.worker(httpx2.MockTransport(timeout), True).run_once() == "completed"
    report = harness.owner.get(f"/v1/workspaces/{harness.workspace}/investigations/{iid}/report")
    assert (
        report.json()["explanation_source"] == "rules_fallback"
        and "private provider details" not in report.text
    )


def test_stale_claim_cannot_repeat_collection_or_publish_duplicate_report(harness):
    iid, _ = harness.case("healthy")
    worker = harness.worker()
    first = worker.claim()
    job = harness.db.get(Job, first.job_id)
    job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    harness.db.commit()
    second = worker.claim()
    before = len(harness.seen)
    assert worker.process(first) == "superseded"
    assert len(harness.seen) == before
    assert worker.process(second) == "completed"
    assert worker.process(second) == "superseded"
    assert (
        harness.db.scalar(
            select(func.count()).select_from(Report).where(Report.investigation_id == UUID(iid))
        )
        == 1
    )


def test_revoked_requester_is_not_investigated(harness):
    iid, _ = harness.case("healthy")
    member = harness.db.scalar(
        select(Membership).where(Membership.workspace_id == UUID(harness.workspace))
    )
    member.active = False
    harness.db.commit()
    before = len(harness.seen)
    assert harness.worker().run_once() == "failed" and len(harness.seen) == before
    assert harness.db.get(Investigation, UUID(iid)).state == InvestigationState.FAILED
    assert (
        harness.db.scalar(
            select(func.count()).select_from(Report).where(Report.investigation_id == UUID(iid))
        )
        == 0
    )


def test_processing_failure_rolls_back_partial_evidence_and_queues_retry(harness, monkeypatch):
    iid, _ = harness.case("healthy")

    def reject(*_args):
        raise ValueError("synthetic persistence failure")

    monkeypatch.setattr("backend.app.investigations.worker.save_report", reject)
    assert harness.worker().run_once() == "retry_queued"
    assert (
        harness.db.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.investigation_id == UUID(iid))
        )
        == 0
    )
    assert (
        harness.db.scalar(
            select(func.count()).select_from(ToolCall).where(ToolCall.investigation_id == UUID(iid))
        )
        == 0
    )
    job = harness.db.scalar(select(Job).where(Job.investigation_id == UUID(iid)))
    assert job.state == JobState.QUEUED and job.attempts == 1 and job.lease_until is None


def test_quoted_citation_must_match_the_stored_excerpt(harness):
    iid, _ = harness.case("healthy")
    worker = harness.worker()
    claim = worker.claim()
    evidence = Evidence(
        workspace_id=UUID(harness.workspace),
        investigation_id=UUID(iid),
        kind="config",
        title="Known flag",
        source_ref="synthetic:flag",
        excerpt_redacted="exports_enabled=false",
        observed_at=datetime.now(UTC),
    )
    harness.db.add(evidence)
    harness.db.flush()
    report = ReportDraft(
        summary="Test",
        confidence=0.0,
        citations=[{"evidence_id": evidence.id, "quote": "fabricated"}],
    )
    with pytest.raises(ValueError, match="quotes must appear"):
        save_report(harness.db, harness.db.get(Investigation, claim.investigation_id), report)


def test_unknown_job_reference_is_not_substituted_with_another_attempt(harness):
    iid, _ = harness.case("feature_disabled", job_id=str(uuid4()))
    assert harness.worker().run_once() == "inconclusive"
    report = harness.owner.get(
        f"/v1/workspaces/{harness.workspace}/investigations/{iid}/report"
    ).json()
    assert report["root_cause"] is None and any(
        "references" in item for item in report["limitations"]
    )


def test_missing_binding_produces_inconclusive_report_without_model_call(harness):
    iid, _ = harness.case("healthy")
    worker = harness.worker(
        httpx2.MockTransport(
            lambda _: (_ for _ in ()).throw(AssertionError("Unexpected model call"))
        ),
        True,
    )
    worker.diagnostic_settings.bindings_path.unlink()
    before = len(harness.seen)
    assert worker.run_once() == "inconclusive" and len(harness.seen) == before
    report = harness.owner.get(
        f"/v1/workspaces/{harness.workspace}/investigations/{iid}/report"
    ).json()
    assert report["explanation_source"] == "rules" and report["root_cause"] is None


@pytest.mark.parametrize("failure", ["refusal", "length", "malformed", "envelope"])
def test_incomplete_or_refused_model_outputs_keep_the_supported_report(harness, failure):
    iid, _ = harness.case("feature_disabled")

    def invalid(_request):
        if failure == "envelope":
            return response({"unexpected": True})
        message = (
            {"refusal": "No", "content": None}
            if failure == "refusal"
            else {"content": "invalid-json"}
        )
        return response(
            {
                "choices": [
                    {
                        "finish_reason": "length" if failure == "length" else "stop",
                        "message": message,
                    }
                ]
            }
        )

    assert harness.worker(httpx2.MockTransport(invalid), True).run_once() == "completed"
    report = harness.owner.get(
        f"/v1/workspaces/{harness.workspace}/investigations/{iid}/report"
    ).json()
    assert (
        report["explanation_source"] == "rules_fallback"
        and report["root_cause"] == "Exports are disabled for this customer."
    )


def test_exhausted_job_is_failed_without_more_diagnostic_reads(harness):
    iid, _ = harness.case("healthy")
    job = harness.db.scalar(select(Job).where(Job.investigation_id == UUID(iid)))
    job.attempts = job.max_attempts
    harness.db.commit()
    before = len(harness.seen)
    assert harness.worker().run_once() == "failed" and len(harness.seen) == before
    assert harness.db.get(Investigation, UUID(iid)).state == InvestigationState.FAILED


def test_revocation_during_collection_prevents_report_publication(harness):
    iid, _ = harness.case("healthy")
    worker = harness.worker()

    def revoke(_question, baseline, _evidence):
        member = harness.db.scalar(
            select(Membership).where(Membership.workspace_id == UUID(harness.workspace))
        )
        member.active = False
        harness.db.commit()
        return baseline

    worker.explainer.explain = revoke
    assert worker.run_once() == "failed"
    assert (
        harness.db.scalar(
            select(func.count()).select_from(Report).where(Report.investigation_id == UUID(iid))
        )
        == 0
    )
    assert (
        harness.db.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.investigation_id == UUID(iid))
        )
        == 0
    )
