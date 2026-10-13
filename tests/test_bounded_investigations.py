import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import httpx2
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from test_investigation_worker import harness as harness
from test_investigation_worker import model_response, response

from backend.app.investigations.config import InvestigationSettings
from backend.app.models import Job, Membership, ModelCall, Report, ToolCall

DEFAULTS = {
    "investigation_mode": "model_selected",
    "model_input_usd_per_million": "0.1",
    "model_output_usd_per_million": "0.2",
}


def selection(action="logs", reason="continue", **extra):
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {
                            "id": "synthetic-step",
                            "type": "function",
                            "function": {
                                "name": "choose_diagnostic_step",
                                "arguments": json.dumps(
                                    {"action_id": action, "stop_reason": reason, **extra}
                                ),
                            },
                        }
                    ]
                },
            }
        ]
    }


def router(seen=None, bad=None):
    def handle(request):
        payload = json.loads(request.content)
        if seen is not None:
            seen.append(payload)
        if "tools" not in payload:
            return model_response(request)
        assert payload["parallel_tool_calls"] is False
        assert payload["tools"][0]["function"]["strict"] is True
        assert payload["store"] is False and payload["max_completion_tokens"] == 200
        context = json.loads(payload["messages"][1]["content"])
        if bad:
            return response(bad(context))
        available = {item["action_id"] for item in context["available_actions"]}
        action = next(
            name
            for name in ("logs", "features", "permissions", "jobs", "runbooks")
            if name in available
        )
        return response(selection(action))

    return httpx2.MockTransport(handle)


def worker(harness, transport=None, **settings):
    return harness.worker(transport or router(), True, **{**DEFAULTS, **settings})


def job(harness, iid):
    return harness.db.scalar(select(Job).where(Job.investigation_id == UUID(iid)))


def endpoint(harness, iid):
    return f"/v1/workspaces/{harness.workspace}/investigations/{iid}"


@pytest.mark.parametrize(
    "scenario,expected,team",
    [
        ("feature_disabled", "completed", "Account administration"),
        ("permission_removed", "completed", "Account administration"),
        ("job_failed", "completed", "Platform engineering"),
        ("healthy", "completed", "Support engineering"),
        ("ambiguous", "inconclusive", "Platform engineering"),
    ],
)
def test_model_selected_checks_produce_supported_reports_and_dispatch(
    harness, scenario, expected, team
):
    iid, _ = harness.case(scenario)
    seen = []
    assert worker(harness, router(seen)).run_once() == expected
    report = harness.owner.get(endpoint(harness, iid) + "/report").json()
    execution = job(harness, iid)
    assert report["suggested_team"] == team and report["explanation_source"] == "model"
    assert execution.model_call_count == len(seen) <= 6
    assert execution.reserved_model_cost_usd > 0
    audit = harness.owner.get(endpoint(harness, iid) + "/model-calls").json()["items"]
    assert len(audit) == len(seen) and all(item["state"] == "succeeded" for item in audit)
    assert (
        sum(Decimal(item["reserved_cost_usd"]) for item in audit)
        == execution.reserved_model_cost_usd
    )
    assert harness.actor("outsider").get(endpoint(harness, iid) + "/model-calls").status_code == 404
    assert (
        harness.db.scalar(
            select(func.count()).select_from(Report).where(Report.investigation_id == UUID(iid))
        )
        == 1
    )
    assert all(request.method == "GET" for request in harness.seen)
    if scenario == "feature_disabled":
        assert execution.completed_steps == 2 and execution.stop_reason == "sufficient_evidence"
        checks = harness.owner.get(endpoint(harness, iid) + "/tool-calls").json()["items"]
        assert {item["tool_name"] for item in checks} == {"logs", "features"}
    if scenario == "ambiguous":
        assert report["root_cause"] is None and execution.stop_reason == "step_limit"


@pytest.mark.parametrize(
    "bad",
    [
        "unknown",
        "arguments",
        "customer",
        "parallel",
        "repeated",
        "refusal",
        "null_message",
        "contradictory_stop",
    ],
)
def test_invalid_choices_cannot_execute_unapproved_actions(harness, bad):
    iid, _ = harness.case("feature_disabled")

    def invalid(context):
        if bad == "null_message":
            return {"choices": [{"finish_reason": "tool_calls", "message": None}]}
        if bad == "contradictory_stop":
            return selection("logs", "missing_information")
        if bad == "unknown":
            return selection("delete_customer")
        if bad == "arguments":
            return selection("logs", url="https://attacker.invalid", limit=100000)
        if bad == "customer":
            return selection("logs", customer_id="another-workspace-customer")
        if bad == "parallel":
            value = selection()
            value["choices"][0]["message"]["tool_calls"] *= 2
            return value
        if bad == "refusal":
            return {"choices": [{"finish_reason": "stop", "message": {"refusal": "No"}}]}
        # Repeated check: logs is no longer among the available choices on request two.
        return selection("logs")

    assert worker(harness, router(bad=invalid)).run_once() == "completed"
    report = harness.owner.get(endpoint(harness, iid) + "/report").json()
    assert report["root_cause"] == "Exports are disabled for this customer."
    assert any("bounded baseline" in item for item in report["limitations"])
    calls = harness.db.scalars(select(ToolCall).where(ToolCall.investigation_id == UUID(iid))).all()
    assert len({call.tool_name for call in calls}) == len(calls) <= 5
    assert all("attacker" not in str(call.arguments_redacted) for call in calls)
    audit = harness.owner.get(endpoint(harness, iid) + "/model-calls").json()["items"]
    assert any(
        item["state"] == "failed" and item["error_code"] == "invalid_model_choice" for item in audit
    )


def test_model_can_stop_when_information_is_missing(harness):
    iid, _ = harness.case("ambiguous")
    transport = router(bad=lambda _: selection("stop", "missing_information"))
    before = len(harness.seen)
    assert worker(harness, transport).run_once() == "inconclusive"
    assert len(harness.seen) == before
    assert job(harness, iid).stop_reason == "missing_information"
    assert job(harness, iid).model_call_count == 1
    assert harness.owner.get(endpoint(harness, iid) + "/report").json()["root_cause"] is None


def test_step_limit_publishes_partial_evidence_without_an_invented_cause(harness):
    iid, _ = harness.case("feature_disabled")
    assert worker(harness, investigation_max_steps=1).run_once() == "inconclusive"
    assert job(harness, iid).completed_steps == 1 and job(harness, iid).stop_reason == "step_limit"
    assert harness.owner.get(endpoint(harness, iid) + "/report").json()["root_cause"] is None


@pytest.mark.parametrize(
    "settings,reason",
    [
        ({"model_budget_usd": "0.000001"}, "budget_limit"),
        ({"model_input_usd_per_million": None}, "budget_not_configured"),
        ({"model_max_input_token_estimate": 2000}, "context_limit"),
    ],
)
def test_budget_or_input_limit_blocks_requests_before_inference(harness, settings, reason):
    iid, _ = harness.case("healthy")
    seen = []
    assert worker(harness, router(seen), **settings).run_once() == "inconclusive"
    assert seen == [] and job(harness, iid).model_call_count == 0
    assert (
        job(harness, iid).reserved_model_cost_usd == 0 and job(harness, iid).stop_reason == reason
    )


def test_call_limit_also_applies_to_the_explainer(harness):
    iid, _ = harness.case("feature_disabled")
    seen = []
    assert worker(harness, router(seen), model_max_calls=2).run_once() == "completed"
    assert len(seen) == 2 and all("tools" in payload for payload in seen)
    assert job(harness, iid).stop_reason == "budget_limit"
    report = harness.owner.get(endpoint(harness, iid) + "/report").json()
    assert report["explanation_source"] == "rules_fallback" and report["root_cause"]


def test_timeout_has_a_durable_reservation_and_bounded_fallback(harness):
    iid, _ = harness.case("feature_disabled")
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx2.ReadTimeout("token=private-provider-response", request=request)

    assert worker(harness, httpx2.MockTransport(timeout)).run_once() == "completed"
    assert len(calls) <= 2 and job(harness, iid).reserved_model_cost_usd > 0
    audit = harness.owner.get(endpoint(harness, iid) + "/model-calls")
    assert "private-provider-response" not in audit.text
    assert all(item["state"] == "failed" for item in audit.json()["items"])


def test_runtime_limit_stops_before_any_model_or_tool_call(harness, monkeypatch):
    iid, _ = harness.case("healthy")
    monkeypatch.setattr(
        "backend.app.investigations.runner.time", SimpleNamespace(monotonic=lambda: float("inf"))
    )
    seen = []
    before = len(harness.seen)
    assert worker(harness, router(seen)).run_once() == "inconclusive"
    assert seen == [] and len(harness.seen) == before
    assert job(harness, iid).stop_reason == "runtime_limit"


def test_worker_crash_does_not_refund_or_reset_a_reserved_model_call(harness):
    iid, _ = harness.case("healthy")

    def crash(_request):
        raise SystemExit("Process terminated after sending request")

    first = worker(harness, httpx2.MockTransport(crash), model_max_calls=1)
    with pytest.raises(SystemExit):
        first.run_once()
    execution = job(harness, iid)
    charged = execution.reserved_model_cost_usd
    assert execution.model_call_count == 1 and charged > 0
    execution.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    harness.db.commit()
    seen = []
    assert worker(harness, router(seen), model_max_calls=1).run_once() == "inconclusive"
    assert seen == [] and job(harness, iid).attempts == 2
    assert (
        job(harness, iid).model_call_count == 1
        and job(harness, iid).reserved_model_cost_usd == charged
    )
    audit = harness.owner.get(endpoint(harness, iid) + "/model-calls").json()["items"]
    assert len(audit) == 1 and audit[0]["state"] == "reserved"


def test_model_cannot_bypass_exact_job_reference_by_choosing_logs_first(harness):
    from uuid import uuid4

    iid, _ = harness.case("feature_disabled", job_id=str(uuid4()))
    assert worker(harness).run_once() == "inconclusive"
    report = harness.owner.get(endpoint(harness, iid) + "/report").json()
    assert report["root_cause"] is None
    assert any("references" in item for item in report["limitations"])


def test_revocation_after_selection_prevents_the_selected_tool_call(harness):
    iid, _ = harness.case("feature_disabled")

    def revoke(_context):
        member = harness.db.scalar(
            select(Membership).where(Membership.workspace_id == UUID(harness.workspace))
        )
        member.active = False
        harness.db.commit()
        return selection()

    before = len(harness.seen)
    assert worker(harness, router(bad=revoke)).run_once() == "failed"
    assert len(harness.seen) == before
    assert (
        harness.db.scalar(
            select(func.count())
            .select_from(ModelCall)
            .where(ModelCall.investigation_id == UUID(iid))
        )
        == 1
    )
    assert (
        harness.db.scalar(
            select(func.count()).select_from(Report).where(Report.investigation_id == UUID(iid))
        )
        == 0
    )


@pytest.mark.parametrize(
    "values",
    [
        {"investigation_max_steps": 9},
        {"investigation_max_seconds": 61},
        {"model_max_calls": 11},
        {"model_budget_usd": "NaN"},
        {"model_input_usd_per_million": "Infinity"},
        {"model_output_usd_per_million": "-1"},
    ],
)
def test_invalid_execution_limits_are_rejected(values):
    with pytest.raises(ValidationError):
        InvestigationSettings(_env_file=None, **values)
