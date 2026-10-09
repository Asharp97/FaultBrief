from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Investigation


class MembershipRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SUPPORT = "support"
    VIEWER = "viewer"


class InvestigationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IntegrationKind(StrEnum):
    DEMO = "demo"
    LOGS = "logs"
    RUNBOOKS = "runbooks"


class ToolCallState(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceKind(StrEnum):
    LOG = "log"
    CONFIG = "config"
    HEALTH = "health"
    RUNBOOK = "runbook"


class FeedbackRating(StrEnum):
    HELPFUL = "helpful"
    INCORRECT = "incorrect"
    INCOMPLETE = "incomplete"


TRANSITIONS = {
    InvestigationState.QUEUED: {InvestigationState.RUNNING, InvestigationState.FAILED},
    InvestigationState.RUNNING: {
        InvestigationState.COMPLETED,
        InvestigationState.INCONCLUSIVE,
        InvestigationState.FAILED,
    },
    InvestigationState.COMPLETED: set(),
    InvestigationState.INCONCLUSIVE: set(),
    InvestigationState.FAILED: set(),
}


def transition_investigation(
    investigation: "Investigation", target: InvestigationState, now: datetime | None = None
) -> None:
    if target not in TRANSITIONS[InvestigationState(investigation.state)]:
        raise ValueError("Invalid investigation state transition.")
    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("Investigation timestamps must include a timezone.")
    investigation.state = target
    investigation.updated_at = timestamp
    if target == InvestigationState.RUNNING:
        investigation.started_at = timestamp
    else:
        investigation.finished_at = timestamp
