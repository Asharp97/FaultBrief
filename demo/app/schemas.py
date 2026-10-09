from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerSummary(Contract):
    id: UUID
    name: str
    external_id: str


class CustomerRead(CustomerSummary):
    exports_enabled: bool
    config_version: int = Field(ge=1)
    updated_at: datetime


class MemberRead(Contract):
    id: UUID
    customer_id: UUID
    name: str
    role: Literal["analyst", "viewer"]
    permissions: list[str]


class ReportRow(Contract):
    month: str
    revenue_usd: int = Field(ge=0)


class ReportRead(Contract):
    id: UUID
    customer_id: UUID
    title: str
    rows: list[ReportRow]


class JobRead(Contract):
    id: UUID
    customer_id: UUID
    member_id: UUID
    report_id: UUID
    request_id: UUID
    state: Literal["queued", "running", "completed", "failed"]
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class LogRead(Contract):
    id: UUID
    customer_id: UUID
    member_id: UUID
    request_id: UUID
    event: str
    status_code: int = Field(ge=100, le=599)
    message_redacted: str
    observed_at: datetime


class Items[Item](Contract):
    items: list[Item]


class Page[Item](Items[Item]):
    limit: int
    offset: int


class LogsPage(Page[LogRead]):
    coverage: Literal["full", "partial"]
