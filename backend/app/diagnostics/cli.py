import argparse
import json
import os
import time
from contextlib import contextmanager
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import Settings
from ..database import database_engine
from ..domain import IntegrationKind, MembershipRole
from ..models import Customer, Integration, Membership
from .bindings import SECRET_REF, DiagnosticError, Registry, resolve_scope
from .client import DiagnosticTools
from .config import DiagnosticSettings
from .contracts import Features, Scope


@contextmanager
def registry_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + 2
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise DiagnosticError("binding_configuration_busy") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def connect(session, settings, workspace_id, owner_user_id, source_customer_id, *, transport=None):
    """Privileged operator setup: approve one real source customer for one workspace."""
    owner = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == owner_user_id,
            Membership.role == MembershipRole.OWNER,
            Membership.active.is_(True),
        )
    )
    if owner is None:
        raise DiagnosticError("workspace_owner_not_found")
    probe = DiagnosticTools(
        Scope(
            workspace_id=workspace_id,
            customer_id=uuid4(),
            integration_id=uuid4(),
            source_customer_id=source_customer_id,
        ),
        settings,
        transport=transport,
    )
    source_customer_id = probe.scope.source_customer_id
    source = probe._parse(Features, probe._get())
    if source.id != source_customer_id:
        raise DiagnosticError("source_scope_mismatch")
    with registry_lock(settings.bindings_path):
        original = Registry.read(settings.bindings_path)
        occupied = next(
            (item for item in original.bindings if item.source_customer_id == source_customer_id),
            None,
        )
        if occupied and occupied.workspace_id != workspace_id:
            raise DiagnosticError("source_already_assigned")
        customer = session.scalar(
            select(Customer).where(
                Customer.workspace_id == workspace_id,
                Customer.external_id == source.external_id,
            )
        )
        if customer is None:
            customer = Customer(
                workspace_id=workspace_id, name=source.name, external_id=source.external_id
            )
            session.add(customer)
            session.flush()
        if occupied and occupied.customer_id != customer.id:
            raise DiagnosticError("source_already_assigned")
        existing = next(
            (
                item
                for item in original.bindings
                if item.workspace_id == workspace_id and item.customer_id == customer.id
            ),
            None,
        )
        if existing and existing.source_customer_id != source_customer_id:
            raise DiagnosticError("customer_already_connected")
        integration = session.scalar(
            select(Integration)
            .where(
                Integration.workspace_id == workspace_id,
                Integration.kind == IntegrationKind.DEMO,
                Integration.secret_ref == SECRET_REF,
            )
            .order_by(Integration.created_at, Integration.id)
            .limit(1)
        )
        if integration is None:
            integration = Integration(
                workspace_id=workspace_id,
                kind=IntegrationKind.DEMO,
                name="Ledger diagnostics",
                enabled=True,
                secret_ref=SECRET_REF,
            )
            session.add(integration)
            session.flush()
        integration.enabled = True
        binding = Scope(
            workspace_id=workspace_id,
            customer_id=customer.id,
            integration_id=integration.id,
            source_customer_id=source_customer_id,
        )
        registry = Registry(
            bindings=[
                item
                for item in original.bindings
                if (item.workspace_id, item.customer_id) != (workspace_id, customer.id)
            ]
            + [binding]
        )
        registry.save(settings.bindings_path)
        try:
            session.commit()
        except SQLAlchemyError:
            original.save(settings.bindings_path)
            raise
    return binding


def main():
    parser = argparse.ArgumentParser(description="Operator setup and model-free diagnostic reads.")
    commands = parser.add_subparsers(dest="command", required=True)
    binder = commands.add_parser("connect")
    binder.add_argument("--workspace-id", type=UUID, required=True)
    binder.add_argument("--owner-user-id", type=UUID, required=True)
    binder.add_argument("--source-customer-id", type=UUID, required=True)
    reader = commands.add_parser("read")
    reader.add_argument("--workspace-id", type=UUID, required=True)
    reader.add_argument("--customer-id", type=UUID, required=True)
    reader.add_argument(
        "--tool", choices=["permissions", "features", "jobs", "logs", "runbooks"], required=True
    )
    reader.add_argument("--member-id", type=UUID)
    reader.add_argument("--job-id", type=UUID)
    reader.add_argument("--request-id", type=UUID)
    reader.add_argument(
        "--runbook-id", choices=["export-permissions", "export-feature", "export-jobs"]
    )
    reader.add_argument("--limit", type=int)
    reader.add_argument("--query")
    args = parser.parse_args()
    engine = None
    try:
        settings = DiagnosticSettings()
        database = Settings().database_url
        if not database:
            raise DiagnosticError("database_not_configured")
        engine = database_engine(database.get_secret_value())
        with Session(engine, expire_on_commit=False) as session:
            if args.command == "connect":
                binding = connect(
                    session,
                    settings,
                    args.workspace_id,
                    args.owner_user_id,
                    args.source_customer_id,
                )
                print(json.dumps({"status": "connected", **binding.model_dump(mode="json")}))
            else:
                scope = resolve_scope(
                    session, args.workspace_id, args.customer_id, settings.bindings_path
                )
                arguments = {
                    key: value
                    for key in ("member_id", "job_id", "request_id", "runbook_id", "limit", "query")
                    if (value := getattr(args, key)) is not None
                }
                result = DiagnosticTools(scope, settings).run(args.tool, arguments)
                print(result.model_dump_json())
                if result.state == "failed":
                    raise SystemExit(1)
    except DiagnosticError as error:
        print(json.dumps({"status": "failed", "code": error.code}))
        raise SystemExit(1) from None
    except (SQLAlchemyError, ValidationError, OSError):
        print(json.dumps({"status": "failed", "code": "diagnostics_unavailable_or_unconfigured"}))
        raise SystemExit(1) from None
    finally:
        if engine:
            engine.dispose()


if __name__ == "__main__":
    main()
