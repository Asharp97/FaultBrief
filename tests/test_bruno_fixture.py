import runpy
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.domain import InvestigationState, MembershipRole
from backend.app.models import (
    Customer,
    Investigation,
    Job,
    Membership,
    ReportCitation,
    ToolCall,
    User,
    Workspace,
)

seed_fixture = runpy.run_path(str(Path(__file__).parent / "bruno" / "seed_fixture.py"))[
    "seed_fixture"
]


@pytest.fixture
def manual_scope(db_session):
    owner = User(auth_issuer="https://auth.example.invalid", auth_subject=str(uuid4()))
    viewer = User(auth_issuer="https://auth.example.invalid", auth_subject=str(uuid4()))
    workspace = Workspace(name="Bruno manual A - fixture-guard-test")
    db_session.add_all([owner, viewer, workspace])
    db_session.flush()
    membership = Membership(
        workspace_id=workspace.id, user_id=owner.id, role=MembershipRole.OWNER, active=True
    )
    customer = Customer(workspace_id=workspace.id, name="Synthetic customer", external_id="manual")
    db_session.add_all([membership, customer])
    db_session.flush()
    return workspace, customer, owner, viewer


def test_fixture_creates_scoped_read_only_evidence_and_local_viewer(db_session, manual_scope):
    workspace, customer, owner, viewer = manual_scope
    values = seed_fixture(db_session, workspace.id, customer.id, owner.id, viewer.id)
    case = db_session.scalar(
        select(Investigation).where(Investigation.workspace_id == workspace.id)
    )
    assert case.state == InvestigationState.COMPLETED
    assert case.customer_id == customer.id and case.created_by_user_id == owner.id
    assert case.started_at <= case.finished_at
    job = db_session.scalar(select(Job).where(Job.investigation_id == case.id))
    tool = db_session.scalar(select(ToolCall).where(ToolCall.investigation_id == case.id))
    citation = db_session.scalar(
        select(ReportCitation).where(ReportCitation.investigation_id == case.id)
    )
    assert job.attempts == 1 and tool.read_only is True and tool.job_id == job.id
    assert str(citation.evidence_id) == values["fixture_evidence_id"]
    assert str(citation.report_id) == values["fixture_report_id"]
    assert citation.workspace_id == workspace.id
    membership = db_session.scalar(select(Membership).where(Membership.user_id == viewer.id))
    assert membership.role == MembershipRole.VIEWER and membership.active is True


@pytest.mark.parametrize("invalid", ["workspace", "customer", "owner", "existing_role", "revoked"])
def test_fixture_rejects_invalid_scope_without_partial_writes(db_session, manual_scope, invalid):
    workspace, customer, owner, viewer = manual_scope
    if invalid == "workspace":
        workspace.name = "Real customer workspace"
    if invalid in {"existing_role", "revoked"}:
        db_session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=viewer.id,
                role=MembershipRole.ADMIN if invalid == "existing_role" else MembershipRole.VIEWER,
                active=invalid != "revoked",
            )
        )
    db_session.flush()
    with pytest.raises(ValueError):
        seed_fixture(
            db_session,
            workspace.id,
            uuid4() if invalid == "customer" else customer.id,
            viewer.id if invalid == "owner" else owner.id,
            viewer.id,
        )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Investigation)
            .where(Investigation.workspace_id == workspace.id)
        )
        == 0
    )
    viewer_membership = db_session.scalar(select(Membership).where(Membership.user_id == viewer.id))
    if invalid == "existing_role":
        assert viewer_membership.role == MembershipRole.ADMIN
    elif invalid == "revoked":
        assert viewer_membership.active is False
    else:
        assert viewer_membership is None
