"""Operator-only synthetic data for manual Bruno tests; never exposed through HTTP."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

# Allow the documented command to run this file directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.app.config import Settings  # noqa: E402
from backend.app.database import database_engine  # noqa: E402
from backend.app.domain import (  # noqa: E402
    EvidenceKind,
    InvestigationState,
    JobState,
    MembershipRole,
    ToolCallState,
    transition_investigation,
)
from backend.app.models import (  # noqa: E402
    Customer,
    Evidence,
    Investigation,
    Job,
    Membership,
    ToolCall,
    User,
    Workspace,
)
from backend.app.schemas import Citation, ReportDraft  # noqa: E402
from backend.app.services import save_report  # noqa: E402


def seed_fixture(
    session: Session,
    workspace_id: UUID,
    customer_id: UUID,
    owner_user_id: UUID,
    viewer_user_id: UUID | None = None,
) -> dict[str, str]:
    """Validate the manual-test scope, then create a new fixture in one caller-owned transaction."""
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or not workspace.name.startswith("Bruno manual A - "):
        raise ValueError("Use a workspace created by Bruno folder 03 (Bruno manual A - ...).")
    customer = session.get(Customer, customer_id)
    if customer is None or customer.workspace_id != workspace_id:
        raise ValueError("The customer must belong to the supplied manual-test workspace.")
    owner = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == owner_user_id,
            Membership.active.is_(True),
            Membership.role == MembershipRole.OWNER,
        )
    )
    if owner is None:
        raise ValueError("Supply the active owner user ID captured by Bruno user A identity.")

    viewer = None
    if viewer_user_id is not None:
        if viewer_user_id == owner_user_id or session.get(User, viewer_user_id) is None:
            raise ValueError("Provision a different viewer with GET /v1/me first.")
        viewer = session.scalar(
            select(Membership).where(
                Membership.workspace_id == workspace_id,
                Membership.user_id == viewer_user_id,
            )
        )
        if viewer is not None and (viewer.role != MembershipRole.VIEWER or not viewer.active):
            raise ValueError("Refusing to replace an existing role or reactivate a membership.")

    if viewer_user_id is not None and viewer is None:
        session.add(
            Membership(
                workspace_id=workspace_id,
                user_id=viewer_user_id,
                role=MembershipRole.VIEWER,
                active=True,
            )
        )

    investigation = Investigation(
        workspace_id=workspace_id,
        customer_id=customer_id,
        created_by_user_id=owner_user_id,
        question="Synthetic Bruno fixture: why is the example export disabled?",
        state=InvestigationState.QUEUED,
    )
    session.add(investigation)
    session.flush()
    transition_investigation(investigation, InvestigationState.RUNNING)
    session.flush()
    job = Job(
        workspace_id=workspace_id,
        investigation_id=investigation.id,
        state=JobState.COMPLETED,
        attempts=1,
    )
    session.add(job)
    session.flush()
    tool = ToolCall(
        workspace_id=workspace_id,
        investigation_id=investigation.id,
        job_id=job.id,
        integration_id=None,
        tool_name="synthetic_export_config",
        state=ToolCallState.COMPLETED,
        read_only=True,
        arguments_redacted={"synthetic": True},
    )
    session.add(tool)
    session.flush()
    excerpt = "synthetic fixture: exports_enabled=false"
    evidence = Evidence(
        workspace_id=workspace_id,
        investigation_id=investigation.id,
        tool_call_id=tool.id,
        kind=EvidenceKind.CONFIG,
        title="Synthetic export configuration",
        source_ref="fixture://bruno/export-config",
        source_version="manual-v1",
        excerpt_redacted=excerpt,
        observed_at=datetime.now(UTC),
    )
    session.add(evidence)
    session.flush()
    report = save_report(
        session,
        investigation,
        ReportDraft(
            summary="Synthetic fixture: export configuration was inspected.",
            root_cause="Synthetic fixture: exports are disabled for this example customer.",
            confidence=0.95,
            suggested_team="Support",
            limitations=["Synthetic manual-test fixture; no live diagnostics ran."],
            citations=[Citation(evidence_id=evidence.id, quote=excerpt)],
        ),
    )
    transition_investigation(investigation, InvestigationState.COMPLETED)
    session.flush()
    values = {
        "fixture_workspace_id": str(workspace_id),
        "fixture_customer_id": str(customer_id),
        "fixture_investigation_id": str(investigation.id),
        "fixture_report_id": str(report.id),
        "fixture_evidence_id": str(evidence.id),
        "fixture_owner_user_id": str(owner_user_id),
    }
    if viewer_user_id is not None:
        values["fixture_viewer_user_id"] = str(viewer_user_id)
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True, type=UUID)
    parser.add_argument("--customer-id", required=True, type=UUID)
    parser.add_argument("--owner-user-id", required=True, type=UUID)
    parser.add_argument("--viewer-user-id", type=UUID)
    parser.add_argument("--confirm-synthetic-fixture", required=True, action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if settings.faultbrief_environment == "production":
        parser.exit(2, "Refusing fixture creation in production.\n")
    if settings.database_url is None:
        parser.exit(2, "Configure the development database in backend/.env first.\n")
    engine = database_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine, expire_on_commit=False) as session, session.begin():
            values = seed_fixture(
                session,
                args.workspace_id,
                args.customer_id,
                args.owner_user_id,
                args.viewer_user_id,
            )
        print(json.dumps(values, indent=2))
    except ValueError as error:
        parser.exit(2, f"{error}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
