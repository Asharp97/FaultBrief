from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .domain import (
    EvidenceKind,
    FeedbackRating,
    IntegrationKind,
    InvestigationState,
    JobState,
    MembershipRole,
    ToolCallState,
)

SCHEMA = "faultbrief"


class Base(DeclarativeBase):
    metadata = MetaData(
        schema=SCHEMA,
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
        },
    )


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda items: [item.value for item in items],
    )


class Record:
    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Record, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("auth_issuer", "auth_subject"),)
    auth_issuer: Mapped[str] = mapped_column(String(512))
    auth_subject: Mapped[str] = mapped_column(String(255))
    # No passwords, sessions, or duplicated Neon Auth credential storage.


class Workspace(Record, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(120))


class Membership(Record, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("faultbrief.workspaces.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("faultbrief.users.id"))
    role: Mapped[MembershipRole] = mapped_column(enum_type(MembershipRole, "membership_role"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Customer(Record, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id"),
        UniqueConstraint("workspace_id", "external_id"),
        Index("ix_customers_workspace_created", "workspace_id", "created_at", "id"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("faultbrief.workspaces.id"))
    name: Mapped[str] = mapped_column(String(120))
    external_id: Mapped[str] = mapped_column(String(128))


class Integration(Record, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("id", "workspace_id"),)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("faultbrief.workspaces.id"))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[IntegrationKind] = mapped_column(enum_type(IntegrationKind, "integration_kind"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    secret_ref: Mapped[str | None] = mapped_column(String(512))


class Investigation(Record, Base):
    __tablename__ = "investigations"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id"),
        ForeignKeyConstraint(
            ["customer_id", "workspace_id"],
            ["faultbrief.customers.id", "faultbrief.customers.workspace_id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "created_by_user_id"],
            ["faultbrief.memberships.workspace_id", "faultbrief.memberships.user_id"],
        ),
        Index("ix_investigations_workspace_created", "workspace_id", "created_at", "id"),
        CheckConstraint(
            "(state = 'queued' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(state = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(state IN ('completed', 'inconclusive') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL) OR (state = 'failed' AND finished_at IS NOT NULL)",
            name="state_timestamps",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="timestamp_order",
        ),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("faultbrief.workspaces.id"))
    customer_id: Mapped[UUID] = mapped_column()
    created_by_user_id: Mapped[UUID] = mapped_column()
    question: Mapped[str] = mapped_column(Text)
    state: Mapped[InvestigationState] = mapped_column(
        enum_type(InvestigationState, "investigation_state"),
        default=InvestigationState.QUEUED,
        server_default="queued",
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Record, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("investigation_id"),
        UniqueConstraint("id", "investigation_id", "workspace_id"),
        ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["faultbrief.investigations.id", "faultbrief.investigations.workspace_id"],
        ),
        CheckConstraint(
            "attempts >= 0 AND attempts <= max_attempts AND max_attempts > 0", name="attempt_limits"
        ),
        Index("ix_jobs_state_available", "state", "available_at"),
    )
    workspace_id: Mapped[UUID] = mapped_column()
    investigation_id: Mapped[UUID] = mapped_column()
    state: Mapped[JobState] = mapped_column(
        enum_type(JobState, "job_state"), default=JobState.QUEUED, server_default="queued"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolCall(Record, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", "workspace_id"),
        ForeignKeyConstraint(
            ["job_id", "investigation_id", "workspace_id"],
            [
                "faultbrief.jobs.id",
                "faultbrief.jobs.investigation_id",
                "faultbrief.jobs.workspace_id",
            ],
        ),
        ForeignKeyConstraint(
            ["integration_id", "workspace_id"],
            ["faultbrief.integrations.id", "faultbrief.integrations.workspace_id"],
        ),
        CheckConstraint("read_only = true", name="read_only_only"),
    )
    workspace_id: Mapped[UUID] = mapped_column()
    investigation_id: Mapped[UUID] = mapped_column()
    job_id: Mapped[UUID] = mapped_column()
    integration_id: Mapped[UUID | None] = mapped_column()
    tool_name: Mapped[str] = mapped_column(String(80))
    state: Mapped[ToolCallState] = mapped_column(enum_type(ToolCallState, "tool_call_state"))
    read_only: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    arguments_redacted: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class Evidence(Record, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", "workspace_id"),
        ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["faultbrief.investigations.id", "faultbrief.investigations.workspace_id"],
        ),
        ForeignKeyConstraint(
            ["tool_call_id", "investigation_id", "workspace_id"],
            [
                "faultbrief.tool_calls.id",
                "faultbrief.tool_calls.investigation_id",
                "faultbrief.tool_calls.workspace_id",
            ],
        ),
    )
    workspace_id: Mapped[UUID] = mapped_column()
    investigation_id: Mapped[UUID] = mapped_column()
    tool_call_id: Mapped[UUID | None] = mapped_column()
    kind: Mapped[EvidenceKind] = mapped_column(enum_type(EvidenceKind, "evidence_kind"))
    title: Mapped[str] = mapped_column(String(200))
    source_ref: Mapped[str] = mapped_column(String(512))
    source_version: Mapped[str | None] = mapped_column(String(128))
    excerpt_redacted: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Report(Record, Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("investigation_id"),
        UniqueConstraint("id", "investigation_id", "workspace_id"),
        ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["faultbrief.investigations.id", "faultbrief.investigations.workspace_id"],
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )
    workspace_id: Mapped[UUID] = mapped_column()
    investigation_id: Mapped[UUID] = mapped_column()
    summary: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    suggested_team: Mapped[str | None] = mapped_column(String(80))
    limitations: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )


class ReportCitation(Base):
    __tablename__ = "report_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["report_id", "investigation_id", "workspace_id"],
            [
                "faultbrief.reports.id",
                "faultbrief.reports.investigation_id",
                "faultbrief.reports.workspace_id",
            ],
        ),
        ForeignKeyConstraint(
            ["evidence_id", "investigation_id", "workspace_id"],
            [
                "faultbrief.evidence.id",
                "faultbrief.evidence.investigation_id",
                "faultbrief.evidence.workspace_id",
            ],
        ),
    )
    report_id: Mapped[UUID] = mapped_column(primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(primary_key=True)
    investigation_id: Mapped[UUID] = mapped_column()
    workspace_id: Mapped[UUID] = mapped_column()
    quote: Mapped[str | None] = mapped_column(String(800))


class Feedback(Record, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("report_id", "user_id"),
        ForeignKeyConstraint(
            ["report_id", "investigation_id", "workspace_id"],
            [
                "faultbrief.reports.id",
                "faultbrief.reports.investigation_id",
                "faultbrief.reports.workspace_id",
            ],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["faultbrief.memberships.workspace_id", "faultbrief.memberships.user_id"],
        ),
    )
    workspace_id: Mapped[UUID] = mapped_column()
    investigation_id: Mapped[UUID] = mapped_column()
    report_id: Mapped[UUID] = mapped_column()
    user_id: Mapped[UUID] = mapped_column()
    rating: Mapped[FeedbackRating] = mapped_column(enum_type(FeedbackRating, "feedback_rating"))
    comment: Mapped[str | None] = mapped_column(Text)
