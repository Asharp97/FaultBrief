import hashlib
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .auth import Principal
from .domain import MembershipRole
from .models import (
    Evidence,
    Investigation,
    Job,
    Membership,
    Report,
    ReportCitation,
    User,
    Workspace,
)
from .schemas import InvestigationCreate, MembershipUpdate, ReportDraft


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
        found = {
            item.id: item
            for item in session.scalars(
                select(Evidence).where(
                    Evidence.id.in_(evidence_ids),
                    Evidence.workspace_id == investigation.workspace_id,
                    Evidence.investigation_id == investigation.id,
                )
            )
        }
        if set(found) != evidence_ids:
            raise ValueError("Citations must belong to this investigation and workspace.")
        for citation in draft.citations:
            if (
                citation.quote
                and citation.quote not in found[citation.evidence_id].excerpt_redacted
            ):
                raise ValueError("Citation quotes must appear in the cited evidence excerpt.")
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


def enqueue_investigation(
    session: Session, workspace_id: UUID, user_id: UUID, body: InvestigationCreate
) -> Investigation:
    """Atomic case/job creation, with race-safe replay for explicit submission UUIDs."""
    values = body.model_dump(mode="json", exclude={"submission_id"})
    values["context"] = body.context.model_dump(mode="json", exclude_none=True)
    fingerprint = hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    statement = insert(Investigation).values(
        id=uuid4(),
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        customer_id=body.customer_id,
        question=body.question,
        context=values["context"],
        submission_id=body.submission_id,
        submission_fingerprint=fingerprint,
    )
    if body.submission_id:
        statement = statement.on_conflict_do_nothing(
            constraint="uq_investigations_workspace_id_created_by_user_id_submission_id"
        )
    investigation_id = session.scalar(statement.returning(Investigation.id))
    if investigation_id is None:
        investigation = session.scalar(
            select(Investigation).where(
                Investigation.workspace_id == workspace_id,
                Investigation.created_by_user_id == user_id,
                Investigation.submission_id == body.submission_id,
            )
        )
        if investigation.submission_fingerprint != fingerprint:
            raise HTTPException(409, "Submission ID already belongs to a different ticket.")
        return investigation
    session.add(Job(workspace_id=workspace_id, investigation_id=investigation_id))
    session.flush()
    return session.get(Investigation, investigation_id)
