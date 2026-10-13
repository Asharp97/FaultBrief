from dataclasses import dataclass

from ..domain import InvestigationState
from ..schemas import Citation, ReportDraft
from .collect import Collection


@dataclass(frozen=True)
class Finding:
    report: ReportDraft
    state: InvestigationState


def diagnose(collection: Collection) -> Finding:
    facts, limitations, evidence_ids = [], [], []
    features = collection.results.get("features")
    config = features.data if features and features.state == "completed" else None
    request, job, member = collection.request, collection.job, collection.member
    for name, output in collection.results.items():
        if output.state == "failed":
            limitations.append(f"{name.title()} could not be read ({output.code}).")
        if output.truncated:
            limitations.append(
                f"The {name} result reached its bounded limit; older records may be omitted."
            )
    logs = collection.results.get("logs")
    if logs and logs.data.get("coverage") == "partial":
        limitations.append(
            "Request log coverage is partial; downstream diagnostics are unavailable."
        )
    if not collection.results:
        limitations.append("The affected customer has no available approved diagnostic connection.")

    def cite(name, key):
        item = collection.references.get(name, {}).get(str(key))
        if item and item not in evidence_ids:
            evidence_ids.append(item)

    if config:
        facts.append(
            f"Exports are {'enabled' if config['exports_enabled'] else 'disabled'} "
            f"at configuration version {config['config_version']}."
        )
        cite("features", config["id"])
    if member:
        facts.append(
            "The affected member "
            + ("has" if "exports.create" in member["permissions"] else "does not have")
            + " exports.create permission."
        )
        cite("permissions", member["id"])
    if request:
        facts.append(
            f"Request {request['request_id']} recorded {request['event']} "
            f"with HTTP {request['status_code']}."
        )
        cite("logs", request["id"])
    if job:
        facts.append(
            f"Export job {job['id']} is {job['state']}"
            + (f" with {job['error_code']}." if job["error_code"] else ".")
        )
        cite("jobs", job["id"])

    root, confidence, team = None, 0.0, "Support engineering"
    summary = "The collected records do not establish a supported root cause."
    next_steps = [
        "Confirm the affected user and provide the failing request or export job reference.",
        "Collect the missing diagnostic records before selecting a resolution.",
    ]
    state = InvestigationState.INCONCLUSIVE
    if collection.context_mismatch:
        limitations.append("The ticket references could not be matched to the same export.")
    elif (
        request
        and request["event"] == "permission_denied"
        and request["status_code"] == 403
        and member
        and "exports.create" not in member["permissions"]
    ):
        root = "The affected user lacks exports.create permission."
        summary, confidence, team = (
            "The export request was rejected by the affected user's permissions.",
            0.95,
            "Account administration",
        )
        next_steps = [
            "Ask the account administrator to confirm the affected user's intended access.",
            "Review the permission change and grant export access only if authorized.",
            "Ask the affected user to retry after the approved permission change.",
        ]
        cite("runbooks", "export-permissions")
        state = InvestigationState.COMPLETED
    elif (
        request
        and request["event"] == "feature_disabled"
        and request["status_code"] == 409
        and config
        and not config["exports_enabled"]
    ):
        root = "Exports are disabled for this customer."
        summary, confidence, team = (
            "The customer's export setting blocked the observed request.",
            0.95,
            "Account administration",
        )
        next_steps = [
            "Confirm whether exports should be enabled for this customer.",
            "Review the recorded configuration version with the account administrator.",
            "Retry the export after an authorized configuration correction.",
        ]
        cite("runbooks", "export-feature")
        state = InvestigationState.COMPLETED
    elif (
        request
        and job
        and request["event"] == "export_failed"
        and job["state"] == "failed"
        and job["error_code"] == "STORAGE_WRITE_FAILED"
        and "storage rejected the write" in request["message_redacted"].lower()
    ):
        root = "The export job failed because artifact storage rejected its write."
        summary, confidence, team = (
            "The job and correlated request log identify a failed artifact write.",
            0.9,
            "Platform support",
        )
        limitations.append(
            "These records do not establish the underlying infrastructure reason for the "
            "rejected write."
        )
        next_steps = [
            "Send the correlated job and request references to platform support.",
            "Inspect storage access and downstream traces before choosing a fix.",
        ]
        cite("runbooks", "export-jobs")
        state = InvestigationState.COMPLETED
    elif request and job and request["event"] == "export_completed" and job["state"] == "completed":
        summary, confidence = (
            "The observed export completed successfully; these records do not show a "
            "failure for this request.",
            0.8,
        )
        limitations.append(
            "A completed export does not establish that every reported customer issue is resolved."
        )
        next_steps = [
            "Confirm that the report concerns this completed request and affected user.",
            "If the issue persists, provide the specific failing request reference.",
        ]
        state = InvestigationState.COMPLETED
    elif job and job["error_code"] == "EXPORT_TIMEOUT":
        summary, confidence = (
            "The export timed out, but the available evidence does not establish why.",
            0.3,
        )
        limitations.append("EXPORT_TIMEOUT is a symptom, not an established root cause.")
        next_steps = [
            "Collect downstream traces for the correlated request.",
            "Escalate the timeout with the job reference and missing log coverage.",
        ]
        cite("runbooks", "export-jobs")
    elif not request:
        limitations.append(
            "No matching export attempt was found in the bounded request-log window."
        )
    if logs and logs.data.get("coverage") == "partial":
        confidence = min(confidence, 0.8)
    return Finding(
        ReportDraft(
            summary=summary,
            root_cause=root,
            confidence=float(confidence),
            suggested_team=team,
            limitations=limitations[:20],
            observed_facts=facts,
            next_steps=next_steps,
            explanation_source="rules",
            citations=[Citation(evidence_id=item) for item in evidence_ids],
        ),
        state,
    )
