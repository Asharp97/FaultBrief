import json
import os
from pathlib import Path
from uuid import UUID

from pydantic import Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import IntegrationKind
from ..models import Customer, Integration
from .contracts import Contract, Scope

SECRET_REF = "env:DIAGNOSTIC_DEMO_TOKEN"


class DiagnosticError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Registry(Contract):
    version: int = Field(default=1, ge=1, le=1)
    bindings: list[Scope] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def unique_scopes(self):
        scopes = {(item.workspace_id, item.customer_id) for item in self.bindings}
        sources = {item.source_customer_id for item in self.bindings}
        if len(scopes) != len(self.bindings) or len(sources) != len(self.bindings):
            raise ValueError("Each source customer must have one approved workspace binding.")
        return self

    @classmethod
    def read(cls, path: Path):
        try:
            if not path.exists():
                return cls()
            if path.stat().st_size > 262144:
                raise DiagnosticError("invalid_binding_configuration")
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            raise DiagnosticError("invalid_binding_configuration") from None

    def save(self, path: Path):
        # Only the operator command writes this server-private allowlist.
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".temporary")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(self.model_dump(mode="json"), handle, indent=2)
                handle.write("\n")
            os.replace(temporary, path)
        except OSError:
            raise DiagnosticError("binding_configuration_unavailable") from None


def resolve_scope(session: Session, workspace_id: UUID, customer_id: UUID, path: Path) -> Scope:
    customer = session.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.workspace_id == workspace_id,
        )
    )
    if customer is None:
        raise DiagnosticError("customer_not_found")
    matches = [
        entry
        for entry in Registry.read(path).bindings
        if entry.workspace_id == workspace_id and entry.customer_id == customer_id
    ]
    if len(matches) != 1:
        raise DiagnosticError("customer_not_connected")
    scope = matches[0]
    integration = session.scalar(
        select(Integration).where(
            Integration.id == scope.integration_id,
            Integration.workspace_id == workspace_id,
            Integration.enabled.is_(True),
            Integration.kind == IntegrationKind.DEMO,
            Integration.secret_ref == SECRET_REF,
        )
    )
    if integration is None:
        raise DiagnosticError("integration_not_connected")
    return scope
