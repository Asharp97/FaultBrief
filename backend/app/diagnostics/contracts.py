from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Scope(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True)
    workspace_id: UUID
    customer_id: UUID
    integration_id: UUID
    source_customer_id: UUID


class EmptyArgs(Contract):
    pass


class PermissionsArgs(Contract):
    member_id: UUID | None = None


class JobsArgs(Contract):
    job_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=50, strict=True)


class LogsArgs(Contract):
    request_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=50, strict=True)


class RunbooksArgs(Contract):
    runbook_id: Literal["export-permissions", "export-feature", "export-jobs"] | None = None


class ToolResult(Contract):
    tool: Literal["permissions", "features", "jobs", "logs", "runbooks"]
    state: Literal["completed", "failed"]
    code: str | None = None
    data: dict = Field(default_factory=dict)
    truncated: bool = False


class Features(Contract):
    id: UUID
    name: str = Field(max_length=200)
    external_id: str = Field(max_length=128)
    exports_enabled: bool = Field(strict=True)
    config_version: int = Field(ge=1, strict=True)
    updated_at: datetime


class Member(Contract):
    id: UUID
    customer_id: UUID
    name: str = Field(max_length=200)
    role: Literal["analyst", "viewer"]
    permissions: list[str] = Field(max_length=30)


class Members(Contract):
    items: list[Member] = Field(max_length=100)


class SourceJob(Contract):
    id: UUID
    customer_id: UUID
    member_id: UUID
    report_id: UUID
    request_id: UUID
    state: Literal["queued", "running", "completed", "failed"]
    error_code: Literal["STORAGE_WRITE_FAILED", "EXPORT_TIMEOUT"] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class Jobs(Contract):
    items: list[SourceJob] = Field(max_length=50)
    limit: int
    offset: int


class SourceLog(Contract):
    id: UUID
    customer_id: UUID
    member_id: UUID
    request_id: UUID
    event: str = Field(max_length=80)
    status_code: int = Field(ge=100, le=599, strict=True)
    message_redacted: str = Field(max_length=4000)
    observed_at: datetime


class Logs(Contract):
    items: list[SourceLog] = Field(max_length=50)
    limit: int
    offset: int
    coverage: Literal["full", "partial"]


class Runbook(Contract):
    id: Literal["export-permissions", "export-feature", "export-jobs"]
    version: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)


class Runbooks(Contract):
    items: list[Runbook] = Field(max_length=3)
