import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import database_engine
from ..diagnostics.bindings import DiagnosticError, resolve_scope
from ..diagnostics.client import DiagnosticTools
from ..diagnostics.config import DiagnosticSettings
from ..domain import InvestigationState, JobState, MembershipRole, transition_investigation
from ..models import Investigation, Job, Membership
from ..services import save_report
from .collect import collect
from .config import InvestigationSettings
from .explain import Explainer
from .rules import diagnose


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    investigation_id: UUID
    workspace_id: UUID
    customer_id: UUID
    question: str
    context: dict
    attempt: int
    lease_until: datetime


class Worker:
    def __init__(
        self,
        engine,
        settings=None,
        diagnostic_settings=None,
        *,
        tool_transport=None,
        model_transport=None,
        session_factory=None,
    ):
        self.engine = engine
        self.session_factory = session_factory or (lambda: Session(engine, expire_on_commit=False))
        self.settings = settings or InvestigationSettings()
        self.diagnostic_settings = diagnostic_settings or DiagnosticSettings()
        self.tool_transport = tool_transport
        self.explainer = Explainer(self.settings, transport=model_transport)

    @staticmethod
    def eligible(session, investigation, *, lock=False):
        query = select(Membership.id).where(
            Membership.workspace_id == investigation.workspace_id,
            Membership.user_id == investigation.created_by_user_id,
            Membership.active.is_(True),
            Membership.role.in_(
                [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.SUPPORT]
            ),
        )
        if lock:
            query = query.with_for_update()
        return session.scalar(query) is not None

    @staticmethod
    def fail(job, investigation):
        job.state, job.lease_until = JobState.FAILED, None
        if investigation.state in {InvestigationState.QUEUED, InvestigationState.RUNNING}:
            transition_investigation(investigation, InvestigationState.FAILED)

    def claim(self):
        now = datetime.now(UTC)
        with self.session_factory() as session:
            job = session.scalar(
                select(Job)
                .where(
                    or_(
                        and_(Job.state == JobState.QUEUED, Job.available_at <= now),
                        and_(Job.state == JobState.RUNNING, Job.lease_until <= now),
                    )
                )
                .order_by(Job.available_at, Job.created_at, Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            investigation = session.scalar(
                select(Investigation)
                .where(
                    Investigation.id == job.investigation_id,
                    Investigation.workspace_id == job.workspace_id,
                )
                .with_for_update()
            )
            if (
                investigation is None
                or investigation.state
                not in {InvestigationState.QUEUED, InvestigationState.RUNNING}
                or job.attempts >= job.max_attempts
                or not self.eligible(session, investigation)
            ):
                if investigation is not None:
                    self.fail(job, investigation)
                else:
                    job.state, job.lease_until = JobState.FAILED, None
                session.commit()
                return "failed"
            if investigation.state == InvestigationState.QUEUED:
                transition_investigation(investigation, InvestigationState.RUNNING, now)
            job.state, job.attempts = JobState.RUNNING, job.attempts + 1
            job.lease_until = now + timedelta(seconds=self.settings.worker_lease_seconds)
            claim = Claim(
                job.id,
                investigation.id,
                job.workspace_id,
                investigation.customer_id,
                investigation.question,
                dict(investigation.context),
                job.attempts,
                job.lease_until,
            )
            session.commit()
            return claim

    def owned_job(self, session, claim):
        return session.scalar(
            select(Job)
            .where(
                Job.id == claim.job_id,
                Job.state == JobState.RUNNING,
                Job.attempts == claim.attempt,
                Job.lease_until == claim.lease_until,
            )
            .with_for_update()
        )

    def process(self, claim):
        tools, error = None, None
        try:
            with self.session_factory() as session:
                job = self.owned_job(session, claim)
                if job is None:
                    return "superseded"
                investigation = session.get(Investigation, claim.investigation_id)
                if not self.eligible(session, investigation):
                    self.fail(job, investigation)
                    session.commit()
                    return "failed"
                scope = resolve_scope(
                    session,
                    claim.workspace_id,
                    claim.customer_id,
                    self.diagnostic_settings.bindings_path,
                )
            tools = DiagnosticTools(scope, self.diagnostic_settings, transport=self.tool_transport)
        except DiagnosticError as failure:
            error = failure
        collection = collect(claim, tools, error)
        finding = diagnose(collection)
        report = self.explainer.explain(claim.question, finding.report, collection.evidence)
        with self.session_factory() as session:
            job = self.owned_job(session, claim)
            if job is None:
                return "superseded"
            investigation = session.get(Investigation, claim.investigation_id)
            if not self.eligible(session, investigation, lock=True):
                self.fail(job, investigation)
                session.commit()
                return "failed"
            session.add_all(collection.calls)
            session.flush()
            session.add_all(collection.evidence)
            session.flush()
            save_report(session, investigation, report)
            transition_investigation(investigation, finding.state)
            job.state, job.lease_until = JobState.COMPLETED, None
            session.commit()
        return str(finding.state)

    def retry(self, claim):
        with self.session_factory() as session:
            job = self.owned_job(session, claim)
            if job is None:
                return "superseded"
            investigation = session.get(Investigation, claim.investigation_id)
            if job.attempts >= job.max_attempts:
                self.fail(job, investigation)
            else:
                job.state, job.lease_until = JobState.QUEUED, None
                job.available_at = datetime.now(UTC) + timedelta(seconds=5 * job.attempts)
            session.commit()
            return "retry_queued" if job.state == JobState.QUEUED else "failed"

    def run_once(self):
        claim = self.claim()
        if claim is None or claim == "failed":
            return claim
        try:
            return self.process(claim)
        except (SQLAlchemyError, ValueError, TypeError, AttributeError, RuntimeError, OSError):
            return self.retry(claim)


def main():
    parser = argparse.ArgumentParser(
        description="Process queued investigations with bounded read-only diagnostics."
    )
    parser.add_argument("--once", action="store_true", help="Process at most one job, then exit.")
    args = parser.parse_args()
    engine = None
    try:
        settings = InvestigationSettings()
        if settings.database_url is None:
            raise ValueError("Database configuration required.")
        engine = database_engine(settings.database_url.get_secret_value())
        worker = Worker(engine, settings)
        while True:
            status = worker.run_once()
            if status:
                print(json.dumps({"worker": "investigation", "status": status}), flush=True)
            if args.once:
                break
            if status is None:
                time.sleep(settings.worker_poll_seconds)
    except KeyboardInterrupt:
        pass
    except (SQLAlchemyError, ValueError, OSError):
        print("Investigation worker unavailable. Check server configuration and migrations.")
        raise SystemExit(1) from None
    finally:
        if engine:
            engine.dispose()


if __name__ == "__main__":
    main()
