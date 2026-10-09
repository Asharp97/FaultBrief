from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .auth import Principal
from .domain import MembershipRole
from .models import Evidence, Investigation, Membership, Report, ReportCitation, User, Workspace
from .schemas import MembershipUpdate, ReportDraft


def provision_user(session: Session, principal: Principal) -> User:
    session.execute(
        insert(User)
        .values(auth_issuer=principal.issuer, auth_subject=principal.subject)
        .on_conflict_do_nothing(index_elements=[User.auth_issuer, User.auth_subject])
    )
    user = session.scalar(
        select(User).where(
            User.auth_issuer == principal.issuer, User.auth_subject == principal.subject
        )
    )
    if user is None:
        raise RuntimeError("Identity provisioning did not produce a user.")
    return user


def workspace_membership(session: Session, principal: Principal, workspace_id: UUID) -> Membership:
    membership = session.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.workspace_id == workspace_id,
            Membership.active.is_(True),
            User.auth_issuer == principal.issuer,
            User.auth_subject == principal.subject,
        )
        .execution_options(populate_existing=True)
    )
    if membership is None:
        raise HTTPException(404, "Workspace not found.")
    return membership


def require_writer(membership: Membership) -> None:
    if membership.role not in {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.SUPPORT}:
        raise HTTPException(403, "This workspace role cannot create investigations or resources.")


def require_owner_workspace(session: Session, principal: Principal, workspace_id: UUID) -> None:
    """Serialize membership writes, then recheck the actor under the workspace lock."""
    membership = workspace_membership(session, principal, workspace_id)
    if membership.role != MembershipRole.OWNER:
        raise HTTPException(403, "Only workspace owners can manage memberships.")
    session.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    membership = workspace_membership(session, principal, workspace_id)
    if membership.role != MembershipRole.OWNER:
        raise HTTPException(403, "Only workspace owners can manage memberships.")


def update_membership(session: Session, membership: Membership, body: MembershipUpdate) -> None:
    """Caller holds the workspace lock; retain inactive rows for historical references."""
    next_role = body.role if body.role is not None else membership.role
    next_active = body.active if body.active is not None else membership.active
    if membership.active and membership.role == MembershipRole.OWNER:
        if not next_active or next_role != MembershipRole.OWNER:
            other_owners = session.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.workspace_id == membership.workspace_id,
                    Membership.id != membership.id,
                    Membership.role == MembershipRole.OWNER,
                    Membership.active.is_(True),
                )
            )
            if not other_owners:
                raise HTTPException(409, "A workspace must keep at least one active owner.")
    membership.role = next_role
    membership.active = next_active


def scoped_investigation(
    session: Session, workspace_id: UUID, investigation_id: UUID
) -> Investigation:
    investigation = session.scalar(
        select(Investigation).where(
            Investigation.id == investigation_id,
            Investigation.workspace_id == workspace_id,
        )
    )
    if investigation is None:
        raise HTTPException(404, "Investigation not found.")
    return investigation


def save_report(session: Session, investigation: Investigation, draft: ReportDraft) -> Report:
    """Internal worker operation; validation precedes persistence, caller owns the transaction."""
    evidence_ids = {item.evidence_id for item in draft.citations}
    if evidence_ids:
        found = set(
            session.scalars(
                select(Evidence.id).where(
                    Evidence.id.in_(evidence_ids),
                    Evidence.workspace_id == investigation.workspace_id,
                    Evidence.investigation_id == investigation.id,
                )
            )
        )
        if found != evidence_ids:
            raise ValueError("Citations must belong to this investigation and workspace.")
    report = Report(
        workspace_id=investigation.workspace_id,
        investigation_id=investigation.id,
        **draft.model_dump(exclude={"citations"}),
    )
    session.add(report)
    session.flush()
    session.add_all(
        [
            ReportCitation(
                report_id=report.id,
                evidence_id=item.evidence_id,
                investigation_id=investigation.id,
                workspace_id=investigation.workspace_id,
                quote=item.quote,
            )
            for item in draft.citations
        ]
    )
    session.flush()
    return report
