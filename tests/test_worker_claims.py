from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.app.domain import MembershipRole
from backend.app.investigations.config import InvestigationSettings
from backend.app.investigations.worker import Worker
from backend.app.models import Customer, Investigation, Job, Membership, User, Workspace


def test_parallel_workers_claim_different_jobs_on_real_connections(postgres_engine):
    wid, uid, cid = uuid4(), uuid4(), uuid4()
    try:
        with Session(postgres_engine) as session:
            session.add_all(
                [
                    Workspace(id=wid, name="Concurrent worker lab"),
                    User(id=uid, auth_issuer="https://auth.invalid", auth_subject=str(uid)),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Membership(workspace_id=wid, user_id=uid, role=MembershipRole.OWNER),
                    Customer(id=cid, workspace_id=wid, name="Customer", external_id=str(cid)),
                ]
            )
            session.flush()
            ids = [uuid4(), uuid4()]
            for iid in ids:
                session.add(
                    Investigation(
                        id=iid,
                        workspace_id=wid,
                        customer_id=cid,
                        created_by_user_id=uid,
                        question="Why did exports fail?",
                    )
                )
            session.flush()
            for iid in ids:
                session.add(Job(workspace_id=wid, investigation_id=iid))
            session.commit()
        settings = InvestigationSettings(
            _env_file=None, model_provider=None, model_name=None, ai_provider_api_key=None
        )
        workers = [Worker(postgres_engine, settings) for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker.claim) for worker in workers]
            claims = [future.result(timeout=15) for future in futures]
        assert {claim.investigation_id for claim in claims} == set(ids)
        assert len({claim.job_id for claim in claims}) == 2
        assert all(claim.attempt == 1 for claim in claims)
    finally:
        with postgres_engine.begin() as connection:
            for model in (Job, Investigation, Customer, Membership):
                connection.execute(delete(model).where(model.workspace_id == wid))
            connection.execute(delete(Workspace).where(Workspace.id == wid))
            connection.execute(delete(User).where(User.id == uid))


def test_concurrent_submission_replays_create_only_one_job(postgres_engine):
    from sqlalchemy import func, select

    from backend.app.schemas import InvestigationCreate
    from backend.app.services import enqueue_investigation

    wid, uid, cid = uuid4(), uuid4(), uuid4()
    try:
        with Session(postgres_engine) as session:
            session.add_all(
                [
                    Workspace(id=wid, name="Replay lab"),
                    User(id=uid, auth_issuer="https://auth.invalid", auth_subject=str(uid)),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Membership(workspace_id=wid, user_id=uid, role=MembershipRole.OWNER),
                    Customer(id=cid, workspace_id=wid, name="Customer", external_id=str(cid)),
                ]
            )
            session.commit()
        body = InvestigationCreate(
            customer_id=cid, question="Why did exports fail?", submission_id=uuid4()
        )

        def submit():
            with Session(postgres_engine, expire_on_commit=False) as session:
                item = enqueue_investigation(session, wid, uid, body)
                session.commit()
                return item.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit) for _ in range(2)]
            ids = [future.result(timeout=15) for future in futures]
        assert ids[0] == ids[1]
        with Session(postgres_engine) as session:
            assert (
                session.scalar(select(func.count()).select_from(Job).where(Job.workspace_id == wid))
                == 1
            )
            other = enqueue_investigation(
                session, wid, uid, body.model_copy(update={"submission_id": uuid4()})
            )
            session.commit()
            assert other.id != ids[0]
    finally:
        with postgres_engine.begin() as connection:
            for model in (Job, Investigation, Customer, Membership):
                connection.execute(delete(model).where(model.workspace_id == wid))
            connection.execute(delete(Workspace).where(Workspace.id == wid))
            connection.execute(delete(User).where(User.id == uid))
