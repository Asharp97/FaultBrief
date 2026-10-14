import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from test_investigation_worker import TOKEN
from test_investigation_worker import harness as harness

from backend.app.diagnostics.bindings import DiagnosticError, resolve_scope
from backend.app.domain import MembershipRole
from backend.app.models import Customer, Investigation, Membership
from demo.app.config import DemoSettings
from demo.evaluation.prepare import prepare


def demo_settings(**values):
    return DemoSettings(
        _env_file=None,
        environment="test",
        diagnostic_token=TOKEN,
        operator_token="synthetic-operator-" + "o" * 32,
        app_token="synthetic-app-" + "a" * 32,
        **values,
    )


@pytest.mark.parametrize(
    "scenario", ["healthy", "permission_removed", "feature_disabled", "job_failed", "ambiguous"]
)
def test_operator_connects_observable_sample_without_submitting_or_exposing_answers(
    harness, tmp_path, scenario
):
    answers = tmp_path / "private/answers.jsonl"
    result = prepare(
        harness.db,
        harness.diagnostics,
        demo_settings(),
        UUID(harness.workspace),
        harness.owner_id,
        scenario,
        transport=harness.transport,
        answer_path=answers,
    )
    assert result["status"] == "connected" and result["customer_id"] != result["source_customer_id"]
    approved = resolve_scope(
        harness.db,
        UUID(harness.workspace),
        UUID(result["customer_id"]),
        harness.diagnostics.bindings_path,
    )
    assert str(approved.source_customer_id) == result["source_customer_id"]
    page = harness.owner.get(f"/v1/workspaces/{harness.workspace}/customers").json()
    assert result["customer_id"] in {item["id"] for item in page["items"]}
    assert harness.db.scalar(select(func.count()).select_from(Investigation)) == 0
    assert (
        answers.exists()
        and json.loads(answers.read_text())["customer_id"] == result["source_customer_id"]
    )
    assert all(
        value not in json.dumps(result)
        for value in ("expected_root_cause", "expected_investigation_state", "fault_mode", TOKEN)
    )
    assert (
        sum(
            request.method == "POST" and request.url.path == "/lab/runs" for request in harness.seen
        )
        == 1
    )
    # The operator action is separate; the investigation receives only observed references.
    ticket = harness.owner.post(
        f"/v1/workspaces/{harness.workspace}/investigations",
        json={
            "customer_id": result["customer_id"],
            "question": result["question"],
            "context": result["context"],
        },
    )
    assert ticket.status_code == 201
    before = len(harness.seen)
    assert harness.worker(model_explanation_enabled=False).run_once() == (
        "inconclusive" if scenario == "ambiguous" else "completed"
    )
    assert all(
        request.method == "GET" and not request.url.path.startswith("/lab/")
        for request in harness.seen[before:]
    )
    assert (
        harness.owner.get(
            f"/v1/workspaces/{harness.workspace}/investigations/{ticket.json()['id']}/report"
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "invalid", ["foreign_owner", "inactive", "viewer", "production", "remote", "key_mismatch"]
)
def test_operator_setup_rejects_invalid_scope_before_creating_a_sample(harness, tmp_path, invalid):
    config, uid = harness.diagnostics, harness.owner_id
    if invalid == "foreign_owner":
        uid = uuid4()
    if invalid in {"inactive", "viewer"}:
        membership = harness.db.scalar(
            select(Membership).where(Membership.workspace_id == UUID(harness.workspace))
        )
        if invalid == "inactive":
            membership.active = False
        else:
            membership.role = MembershipRole.VIEWER
        harness.db.commit()
    if invalid == "production":
        config = config.model_copy(update={"environment": "production"})
    if invalid == "remote":
        config = config.model_copy(update={"demo_url": "https://remote.invalid"})
    if invalid == "key_mismatch":
        config = config.model_copy(update={"demo_token": demo_settings().operator_token})
    before = len(harness.seen)
    with pytest.raises(DiagnosticError):
        prepare(
            harness.db,
            config,
            demo_settings(),
            UUID(harness.workspace),
            uid,
            transport=harness.transport,
            answer_path=tmp_path / "private.jsonl",
        )
    assert len(harness.seen) == before
    assert harness.db.scalar(select(func.count()).select_from(Customer)) == 0
    assert not (tmp_path / "private.jsonl").exists()
