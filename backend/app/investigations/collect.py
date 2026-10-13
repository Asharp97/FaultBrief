import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ..diagnostics.bindings import DiagnosticError
from ..diagnostics.client import DiagnosticTools
from ..diagnostics.contracts import ToolResult
from ..domain import EvidenceKind, ToolCallState
from ..models import Evidence, ToolCall

ATTEMPT_EVENTS = {
    "permission_denied",
    "feature_disabled",
    "export_failed",
    "export_completed",
    "export_queued",
}


@dataclass
class Collection:
    calls: list[ToolCall] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    results: dict[str, ToolResult] = field(default_factory=dict)
    references: dict[str, dict[str, UUID]] = field(default_factory=dict)
    request: dict | None = None
    job: dict | None = None
    member: dict | None = None
    context_mismatch: bool = False


def collect(
    claim, tools: DiagnosticTools | None, error: DiagnosticError | None = None
) -> Collection:
    result = Collection()
    scope = tools.scope if tools else None
    context = claim.context
    if tools is None:
        result.calls.append(
            ToolCall(
                id=uuid4(),
                workspace_id=claim.workspace_id,
                investigation_id=claim.investigation_id,
                job_id=claim.job_id,
                integration_id=None,
                tool_name="resolve_customer",
                state=ToolCallState.FAILED,
                arguments_redacted={
                    "customer_id": str(claim.customer_id),
                    "code": error.code if error else "customer_not_connected",
                },
            )
        )
        return result

    def read(name, args):
        output = tools.run(name, args)
        call = ToolCall(
            id=uuid4(),
            workspace_id=claim.workspace_id,
            investigation_id=claim.investigation_id,
            job_id=claim.job_id,
            integration_id=scope.integration_id,
            tool_name=name,
            state=ToolCallState.COMPLETED if output.state == "completed" else ToolCallState.FAILED,
            arguments_redacted={**args, **({"code": output.code} if output.code else {})},
        )
        result.calls.append(call)
        result.results[name] = output
        result.references[name] = {}
        if output.state != "completed":
            return output
        rows = output.data.get("items", []) if name != "features" else [output.data]
        for row in rows:
            kind = (
                EvidenceKind.RUNBOOK
                if name == "runbooks"
                else EvidenceKind.LOG
                if name == "logs"
                else EvidenceKind.CONFIG
                if name in {"features", "permissions"}
                else EvidenceKind.HEALTH
            )
            key = str(row["id"])
            if name == "runbooks":
                source, version, excerpt = f"runbook:ledger/{key}", row["version"], row["content"]
                observed = datetime.now(UTC)
            else:
                source = f"ledger:customer/{scope.source_customer_id}/{name}/{key}"
                version = str(row["config_version"]) if name == "features" else None
                excerpt = json.dumps(row, sort_keys=True, ensure_ascii=False)
                observed = datetime.fromisoformat(
                    row.get("observed_at")
                    or row.get("updated_at")
                    or row.get("created_at")
                    or datetime.now(UTC).isoformat()
                )
            item = Evidence(
                id=uuid4(),
                workspace_id=claim.workspace_id,
                investigation_id=claim.investigation_id,
                tool_call_id=call.id,
                kind=kind,
                title=f"{name.title()}: {key}",
                source_ref=source,
                source_version=version,
                excerpt_redacted=excerpt,
                observed_at=observed,
            )
            result.evidence.append(item)
            result.references[name][key] = item.id
        return output

    read("features", {})
    jobs = read("jobs", {"job_id": context["job_id"]} if context.get("job_id") else {"limit": 5})
    job_rows = jobs.data.get("items", [])
    filtered_jobs = [
        row
        for row in job_rows
        if (not context.get("member_id") or row["member_id"] == context["member_id"])
        and (not context.get("request_id") or row["request_id"] == context["request_id"])
    ]
    if context.get("job_id") and not filtered_jobs:
        result.context_mismatch = True
    result.job = filtered_jobs[0] if filtered_jobs else None
    request_id = context.get("request_id") or (
        result.job["request_id"] if context.get("job_id") and result.job else None
    )
    logs = read("logs", {"limit": 10, **({"request_id": request_id} if request_id else {})})
    log_rows = [
        row
        for row in logs.data.get("items", [])
        if row["event"] in ATTEMPT_EVENTS
        and (not context.get("member_id") or row["member_id"] == context["member_id"])
    ]
    result.request = log_rows[0] if log_rows else None
    if result.request:
        result.job = next(
            (row for row in filtered_jobs if row["request_id"] == result.request["request_id"]),
            None,
        )
    member_id = context.get("member_id") or (result.request or result.job or {}).get("member_id")
    members = read("permissions", {"member_id": member_id} if member_id else {})
    result.member = next(
        (row for row in members.data.get("items", []) if row["id"] == member_id), None
    )
    read("runbooks", {})
    return result
