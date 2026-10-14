import json
import re
import time

import httpx2
from pydantic import ValidationError

from .bindings import DiagnosticError
from .config import DiagnosticSettings
from .contracts import (
    EmptyArgs,
    Features,
    Jobs,
    JobsArgs,
    Logs,
    LogsArgs,
    Members,
    PermissionsArgs,
    RunbooksArgs,
    Scope,
    SourceJob,
    ToolResult,
)
from .runbooks import search_runbooks


def redact(value: str, max_chars: int = 1000) -> str:
    value = re.sub(r"(?i)\bBearer\s+[^\s\"']+", "Bearer [redacted]", value)
    value = re.sub(
        r"(?i)\b(password|secret|token|api[_ -]?key)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", value
    )
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email redacted]", value)
    return value[:max_chars]


class DiagnosticTools:
    def __init__(self, scope: Scope, settings: DiagnosticSettings, *, transport=None):
        self.scope = scope
        self.settings = settings
        self.transport = transport
        self.requests = 0
        self.deadline = time.monotonic() + settings.total_timeout_seconds

    def _get(self, suffix: str = "", params: dict | None = None):
        if not self.settings.demo_token:
            raise DiagnosticError("connector_not_configured")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DiagnosticError("diagnostic_deadline_exceeded")
        if self.requests >= self.settings.max_requests:
            raise DiagnosticError("request_budget_exceeded")
        self.requests += 1
        url = f"{self.settings.demo_url}/v1/customers/{self.scope.source_customer_id}{suffix}"
        try:
            with httpx2.Client(
                trust_env=False, follow_redirects=False, transport=self.transport
            ) as client:
                with client.stream(
                    "GET",
                    url,
                    params=params,
                    timeout=min(
                        remaining,
                        self.settings.request_timeout_seconds,
                    ),
                    headers={
                        "Authorization": f"Bearer {self.settings.demo_token.get_secret_value()}",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if response.status_code != 200:
                        code = {
                            401: "connector_unauthorized",
                            403: "connector_forbidden",
                            404: "source_not_found",
                            429: "connector_rate_limited",
                        }.get(
                            response.status_code,
                            "connector_unavailable",
                        )
                        raise DiagnosticError(code)
                    if (
                        "application/json" not in response.headers.get("content-type", "")
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise DiagnosticError("invalid_source_response")
                    output = bytearray()
                    for chunk in response.iter_raw(chunk_size=8192):
                        if time.monotonic() >= self.deadline:
                            raise DiagnosticError("diagnostic_deadline_exceeded")
                        output.extend(chunk)
                        if len(output) > self.settings.max_response_bytes:
                            raise DiagnosticError("source_response_too_large")
                    return json.loads(output)
        except httpx2.TimeoutException:
            raise DiagnosticError("connector_timeout") from None
        except httpx2.HTTPError:
            raise DiagnosticError("connector_unavailable") from None
        except (ValueError, UnicodeError):
            raise DiagnosticError("invalid_source_response") from None

    def run(self, tool: str, arguments: dict | None = None) -> ToolResult:
        operations = {
            "permissions": self.permissions,
            "features": self.features,
            "jobs": self.jobs,
            "logs": self.logs,
            "runbooks": self.runbooks,
        }
        if tool not in operations:
            raise DiagnosticError("unknown_tool")
        try:
            return operations[tool](arguments or {})
        except ValidationError:
            return ToolResult(tool=tool, state="failed", code="invalid_arguments")
        except DiagnosticError as error:
            return ToolResult(tool=tool, state="failed", code=error.code)

    @staticmethod
    def _parse(model, value):
        try:
            return model.model_validate(value)
        except ValidationError:
            raise DiagnosticError("invalid_source_response") from None

    def _owned(self, items):
        if any(item.customer_id != self.scope.source_customer_id for item in items):
            raise DiagnosticError("source_scope_mismatch")

    def permissions(self, arguments):
        query = PermissionsArgs.model_validate(arguments)
        members = self._parse(Members, self._get("/members")).items
        self._owned(members)
        if any(
            p not in {"reports.read", "exports.create", "exports.download"}
            for member in members
            for p in member.permissions
        ):
            raise DiagnosticError("invalid_source_response")
        if query.member_id:
            members = [item for item in members if item.id == query.member_id]
            if not members:
                raise DiagnosticError("member_not_found")
        data = [
            item.model_dump(mode="json", exclude={"name"})
            for item in members[: self.settings.max_records]
        ]
        return ToolResult(
            tool="permissions",
            state="completed",
            data={"items": data},
            truncated=len(members) > self.settings.max_records,
        )

    def features(self, arguments):
        EmptyArgs.model_validate(arguments)
        item = self._parse(Features, self._get())
        if item.id != self.scope.source_customer_id:
            raise DiagnosticError("source_scope_mismatch")
        return ToolResult(
            tool="features",
            state="completed",
            data=item.model_dump(
                mode="json",
                exclude={"name", "external_id"},
            ),
        )

    def jobs(self, arguments):
        query = JobsArgs.model_validate(arguments)
        limit = min(query.limit, self.settings.max_records)
        if query.job_id:
            item = self._parse(SourceJob, self._get(f"/jobs/{query.job_id}"))
            if item.id != query.job_id:
                raise DiagnosticError("source_scope_mismatch")
            items, truncated = [item], False
        else:
            page = self._parse(Jobs, self._get("/jobs", {"limit": limit, "offset": 0}))
            if page.limit != limit or page.offset != 0 or len(page.items) > limit:
                raise DiagnosticError("invalid_source_response")
            items, truncated = page.items, len(page.items) == limit
        self._owned(items)
        return ToolResult(
            tool="jobs",
            state="completed",
            data={
                "items": [item.model_dump(mode="json") for item in items],
            },
            truncated=truncated,
        )

    def logs(self, arguments):
        query = LogsArgs.model_validate(arguments)
        limit = min(query.limit, self.settings.max_records)
        params = {"limit": limit, "offset": 0}
        if query.request_id:
            params["request_id"] = str(query.request_id)
        page = self._parse(Logs, self._get("/logs", params))
        self._owned(page.items)
        if (
            page.limit != limit
            or page.offset != 0
            or len(page.items) > limit
            or (
                query.request_id and any(item.request_id != query.request_id for item in page.items)
            )
        ):
            raise DiagnosticError("source_scope_mismatch")
        items = []
        for item in page.items:
            data = item.model_dump(mode="json")
            message = data["message_redacted"]
            if self.settings.demo_token:
                message = message.replace(self.settings.demo_token.get_secret_value(), "[redacted]")
            data["message_redacted"] = redact(message)
            items.append(data)
        return ToolResult(
            tool="logs",
            state="completed",
            data={
                "items": items,
                "coverage": page.coverage,
            },
            truncated=len(items) == limit,
        )

    def runbooks(self, arguments):
        query = RunbooksArgs.model_validate(arguments)
        data, truncated = search_runbooks(self.settings.runbooks_path, query)
        for item in data["items"]:
            content = item["content"]
            if self.settings.demo_token:
                content = content.replace(self.settings.demo_token.get_secret_value(), "[redacted]")
            item["content"] = redact(content, max_chars=4000)
        return ToolResult(tool="runbooks", state="completed", data=data, truncated=truncated)
