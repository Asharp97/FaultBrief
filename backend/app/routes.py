from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal, require_principal
from .database import get_session
from .domain import InvestigationState, MembershipRole
from .models import (
    Customer,
    Evidence,
    Feedback,
    Integration,
    Investigation,
    Job,
    Membership,
    Report,
    ReportCitation,
    ToolCall,
    User,
    Workspace,
)
from .schemas import (
    CustomerCreate,
    CustomerRead,
    ErrorResponse,
    EvidenceRead,
    FeedbackCreate,
    FeedbackRead,
    IntegrationCreate,
    IntegrationRead,
    InvestigationCreate,
    InvestigationRead,
    JobRead,
    MembershipRead,
    Page,
    ReportRead,
    ToolCallRead,
    UserRead,
    WorkspaceCreate,
    WorkspaceRead,
)
from .services import provision_user, require_writer, scoped_investigation, workspace_membership

router = APIRouter(
    prefix="/v1",
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 503)},
)
DB = Annotated[Session, Depends(get_session)]
Identity = Annotated[Principal, Depends(require_principal)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10000)]


def page(session: Session, statement, limit: int, offset: int) -> dict:
    return {
        "items": list(session.scalars(statement.limit(limit).offset(offset))),
        "limit": limit,
        "offset": offset,
    }


@router.get("/me", response_model=UserRead, tags=["identity"])
def me(principal: Identity, session: DB):
    user = provision_user(session, principal)
    session.commit()
    return user


@router.post("/workspaces", response_model=WorkspaceRead, status_code=201, tags=["workspaces"])
def create_workspace(body: WorkspaceCreate, principal: Identity, session: DB):
    user = provision_user(session, principal)
    workspace = Workspace(name=body.name)
    session.add(workspace)
    session.flush()
    session.add(Membership(workspace_id=workspace.id, user_id=user.id, role=MembershipRole.OWNER))
    session.commit()
    return workspace


@router.get("/workspaces", response_model=Page[WorkspaceRead], tags=["workspaces"])
def list_workspaces(principal: Identity, session: DB, limit: Limit = 50, offset: Offset = 0):
    statement = (
        select(Workspace)
        .join(Membership)
        .join(User)
        .where(
            User.auth_subject == principal.subject,
            User.auth_issuer == principal.issuer,
            Membership.active.is_(True),
        )
        .order_by(Workspace.created_at, Workspace.id)
    )
    return page(session, statement, limit, offset)


@router.get(
    "/workspaces/{workspace_id}/memberships",
    response_model=Page[MembershipRead],
    tags=["workspaces"],
)
def list_memberships(
    workspace_id: UUID, principal: Identity, session: DB, limit: Limit = 50, offset: Offset = 0
):
    workspace_membership(session, principal, workspace_id)
    return page(
        session,
        select(Membership)
        .where(Membership.workspace_id == workspace_id)
        .order_by(Membership.created_at, Membership.id),
        limit,
        offset,
    )


@router.post(
    "/workspaces/{workspace_id}/customers",
    response_model=CustomerRead,
    status_code=201,
    tags=["customers"],
)
def create_customer(workspace_id: UUID, body: CustomerCreate, principal: Identity, session: DB):
    require_writer(workspace_membership(session, principal, workspace_id))
    customer = Customer(workspace_id=workspace_id, **body.model_dump())
    session.add(customer)
    session.commit()
    return customer


@router.get(
    "/workspaces/{workspace_id}/customers", response_model=Page[CustomerRead], tags=["customers"]
)
def list_customers(
    workspace_id: UUID, principal: Identity, session: DB, limit: Limit = 50, offset: Offset = 0
):
    workspace_membership(session, principal, workspace_id)
    return page(
        session,
        select(Customer)
        .where(Customer.workspace_id == workspace_id)
        .order_by(Customer.created_at, Customer.id),
        limit,
        offset,
    )


@router.get(
    "/workspaces/{workspace_id}/customers/{customer_id}",
    response_model=CustomerRead,
    tags=["customers"],
)
def get_customer(workspace_id: UUID, customer_id: UUID, principal: Identity, session: DB):
    workspace_membership(session, principal, workspace_id)
    customer = session.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.workspace_id == workspace_id)
    )
    if customer is None:
        raise HTTPException(404, "Customer not found.")
    return customer


@router.post(
    "/workspaces/{workspace_id}/integrations",
    response_model=IntegrationRead,
    status_code=201,
    tags=["integrations"],
)
def create_integration(
    workspace_id: UUID, body: IntegrationCreate, principal: Identity, session: DB
):
    membership = workspace_membership(session, principal, workspace_id)
    if membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN}:
        raise HTTPException(403, "Only workspace administrators can configure integrations.")
    integration = Integration(workspace_id=workspace_id, enabled=False, **body.model_dump())
    session.add(integration)
    session.commit()
    return integration


@router.get(
    "/workspaces/{workspace_id}/integrations",
    response_model=Page[IntegrationRead],
    tags=["integrations"],
)
def list_integrations(
    workspace_id: UUID, principal: Identity, session: DB, limit: Limit = 50, offset: Offset = 0
):
    workspace_membership(session, principal, workspace_id)
    return page(
        session,
        select(Integration)
        .where(Integration.workspace_id == workspace_id)
        .order_by(Integration.created_at, Integration.id),
        limit,
        offset,
    )


@router.post(
    "/workspaces/{workspace_id}/investigations",
    response_model=InvestigationRead,
    status_code=201,
    tags=["investigations"],
)
def create_investigation(
    workspace_id: UUID, body: InvestigationCreate, principal: Identity, session: DB
):
    membership = workspace_membership(session, principal, workspace_id)
    require_writer(membership)
    customer = session.scalar(
        select(Customer).where(
            Customer.id == body.customer_id, Customer.workspace_id == workspace_id
        )
    )
    if customer is None:
        raise HTTPException(404, "Customer not found.")
    investigation = Investigation(
        workspace_id=workspace_id,
        customer_id=customer.id,
        created_by_user_id=membership.user_id,
        question=body.question,
        state=InvestigationState.QUEUED,
    )
    session.add(investigation)
    session.flush()
    session.add(Job(workspace_id=workspace_id, investigation_id=investigation.id))
    session.commit()
    return investigation


@router.get(
    "/workspaces/{workspace_id}/investigations",
    response_model=Page[InvestigationRead],
    tags=["investigations"],
)
def list_investigations(
    workspace_id: UUID, principal: Identity, session: DB, limit: Limit = 50, offset: Offset = 0
):
    workspace_membership(session, principal, workspace_id)
    return page(
        session,
        select(Investigation)
        .where(Investigation.workspace_id == workspace_id)
        .order_by(Investigation.created_at, Investigation.id),
        limit,
        offset,
    )


@router.get(
    "/workspaces/{workspace_id}/investigations/{investigation_id}",
    response_model=InvestigationRead,
    tags=["investigations"],
)
def get_investigation(workspace_id: UUID, investigation_id: UUID, principal: Identity, session: DB):
    workspace_membership(session, principal, workspace_id)
    return scoped_investigation(session, workspace_id, investigation_id)


def scoped_rows(model, workspace_id: UUID, investigation_id: UUID):
    return select(model).where(
        model.workspace_id == workspace_id, model.investigation_id == investigation_id
    )


@router.get(
    "/workspaces/{workspace_id}/investigations/{investigation_id}/jobs",
    response_model=Page[JobRead],
    tags=["investigations"],
)
def list_jobs(
    workspace_id: UUID,
    investigation_id: UUID,
    principal: Identity,
    session: DB,
    limit: Limit = 50,
    offset: Offset = 0,
):
    workspace_membership(session, principal, workspace_id)
    scoped_investigation(session, workspace_id, investigation_id)
    return page(
        session, scoped_rows(Job, workspace_id, investigation_id).order_by(Job.id), limit, offset
    )


@router.get(
    "/workspaces/{workspace_id}/investigations/{investigation_id}/tool-calls",
    response_model=Page[ToolCallRead],
    tags=["evidence"],
)
def list_tool_calls(
    workspace_id: UUID,
    investigation_id: UUID,
    principal: Identity,
    session: DB,
    limit: Limit = 50,
    offset: Offset = 0,
):
    workspace_membership(session, principal, workspace_id)
    scoped_investigation(session, workspace_id, investigation_id)
    return page(
        session,
        scoped_rows(ToolCall, workspace_id, investigation_id).order_by(
            ToolCall.created_at, ToolCall.id
        ),
        limit,
        offset,
    )


@router.get(
    "/workspaces/{workspace_id}/investigations/{investigation_id}/evidence",
    response_model=Page[EvidenceRead],
    tags=["evidence"],
)
def list_evidence(
    workspace_id: UUID,
    investigation_id: UUID,
    principal: Identity,
    session: DB,
    limit: Limit = 50,
    offset: Offset = 0,
):
    workspace_membership(session, principal, workspace_id)
    scoped_investigation(session, workspace_id, investigation_id)
    return page(
        session,
        scoped_rows(Evidence, workspace_id, investigation_id).order_by(
            Evidence.created_at, Evidence.id
        ),
        limit,
        offset,
    )


@router.get(
    "/workspaces/{workspace_id}/investigations/{investigation_id}/report",
    response_model=ReportRead,
    tags=["reports"],
)
def get_report(workspace_id: UUID, investigation_id: UUID, principal: Identity, session: DB):
    workspace_membership(session, principal, workspace_id)
    scoped_investigation(session, workspace_id, investigation_id)
    report = session.scalar(scoped_rows(Report, workspace_id, investigation_id))
    if report is None:
        raise HTTPException(404, "Report not found.")
    citations = list(
        session.scalars(
            select(ReportCitation).where(
                ReportCitation.report_id == report.id,
                ReportCitation.workspace_id == workspace_id,
                ReportCitation.investigation_id == investigation_id,
            )
        )
    )
    return ReportRead(
        **{
            field: getattr(report, field)
            for field in ReportRead.model_fields
            if field != "citations"
        },
        citations=citations,
    )


@router.post(
    "/workspaces/{workspace_id}/investigations/{investigation_id}/reports/{report_id}/feedback",
    response_model=FeedbackRead,
    status_code=201,
    tags=["reports"],
)
def create_feedback(
    workspace_id: UUID,
    investigation_id: UUID,
    report_id: UUID,
    body: FeedbackCreate,
    principal: Identity,
    session: DB,
):
    membership = workspace_membership(session, principal, workspace_id)
    scoped_investigation(session, workspace_id, investigation_id)
    report = session.scalar(
        scoped_rows(Report, workspace_id, investigation_id).where(Report.id == report_id)
    )
    if report is None:
        raise HTTPException(404, "Report not found.")
    feedback = Feedback(
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        report_id=report_id,
        user_id=membership.user_id,
        **body.model_dump(),
    )
    session.add(feedback)
    session.commit()
    return feedback
