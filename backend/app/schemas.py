from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import (
    EvidenceKind,
    FeedbackRating,
    IntegrationKind,
    InvestigationState,
    JobState,
    MembershipRole,
    ToolCallState,
)


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", from_attributes=True, str_strip_whitespace=True, allow_inf_nan=False
    )


class Page[T](Contract):
    items: list[T]
    limit: int
    offset: int


class ErrorResponse(Contract):
    detail: str


class RecordRead(Contract):
    id: UUID
    created_at: datetime
    updated_at: datetime


class UserRead(RecordRead):
    pass


class WorkspaceCreate(Contract):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceRead(RecordRead):
    name: str


class MembershipRead(RecordRead):
    workspace_id: UUID
    user_id: UUID
    role: MembershipRole
    active: bool


class CustomerCreate(Contract):
    name: str = Field(min_length=1, max_length=120)
    external_id: str = Field(min_length=1, max_length=128)


class CustomerRead(RecordRead):
    workspace_id: UUID
    name: str
    external_id: str


class IntegrationCreate(Contract):
    name: str = Field(min_length=1, max_length=120)
    kind: IntegrationKind


class IntegrationRead(RecordRead):
    workspace_id: UUID
    name: str
    kind: IntegrationKind
    enabled: bool


class InvestigationCreate(Contract):
    customer_id: UUID
    question: str = Field(min_length=10, max_length=4000)


class InvestigationRead(RecordRead):
    workspace_id: UUID
    customer_id: UUID
    created_by_user_id: UUID
    question: str
    state: InvestigationState
    started_at: datetime | None
    finished_at: datetime | None


class JobRead(RecordRead):
    workspace_id: UUID
    investigation_id: UUID
    state: JobState
    attempts: int
    max_attempts: int
    available_at: datetime


class ToolCallRead(RecordRead):
    workspace_id: UUID
    investigation_id: UUID
    job_id: UUID
    integration_id: UUID | None
    tool_name: str
    state: ToolCallState
    read_only: bool


class EvidenceRead(RecordRead):
    workspace_id: UUID
    investigation_id: UUID
    tool_call_id: UUID | None
    kind: EvidenceKind
    title: str
    source_ref: str
    source_version: str | None
    excerpt_redacted: str
    observed_at: datetime


class Citation(Contract):
    evidence_id: UUID
    quote: str | None = Field(default=None, max_length=800)


class ReportDraft(Contract):
    summary: str = Field(min_length=1, max_length=4000)
    root_cause: str | None = Field(default=None, min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1, strict=True)
    suggested_team: str | None = Field(default=None, min_length=1, max_length=80)
    limitations: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(
        default_factory=list, max_length=20
    )
    citations: list[Citation] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def supported_conclusion(self) -> "ReportDraft":
        if self.root_cause and not self.citations:
            raise ValueError("A root-cause claim requires evidence citations.")
        if len({item.evidence_id for item in self.citations}) != len(self.citations):
            raise ValueError("Evidence citations must be unique.")
        return self


class ReportRead(ReportDraft, RecordRead):
    workspace_id: UUID
    investigation_id: UUID


class FeedbackCreate(Contract):
    rating: FeedbackRating
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackRead(RecordRead):
    workspace_id: UUID
    investigation_id: UUID
    report_id: UUID
    user_id: UUID
    rating: FeedbackRating
    comment: str | None
