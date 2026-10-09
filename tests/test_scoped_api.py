from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.config import Settings
from backend.app.database import get_session
from backend.app.domain import (
    EvidenceKind,
    InvestigationState,
    MembershipRole,
    transition_investigation,
)
from backend.app.main import create_app
from backend.app.models import (
    Evidence,
    Investigation,
    Job,
    Membership,
    Report,
    ReportCitation,
    User,
)
from backend.app.schemas import ReportDraft
from backend.app.services import save_report

ISSUER = "https://auth.example.invalid"


@pytest.fixture
def actors(db_session, postgres_engine):
    settings = Settings(_env_file=None, auth_url=f"{ISSUER}/neondb/auth", jwks_url=f"{ISSUER}/jwks")
    app = create_app(settings, engine=postgres_engine)

    def session_override():
        yield db_session

    app.dependency_overrides[get_session] = session_override
    key = Ed25519PrivateKey.generate()
    app.state.token_verifier.jwks.get_signing_key_from_jwt = lambda _token: SimpleNamespace(
        key=key.public_key(), algorithm_name="EdDSA"
    )

    def actor(subject):
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "iss": ISSUER,
                "sub": subject,
                "iat": now,
                "exp": now + timedelta(minutes=5),
                "role": "owner",
            },
            key,
            algorithm="EdDSA",
            headers={"kid": "test-key"},
        )
        return TestClient(app, headers={"Authorization": f"Bearer {token}"})

    return actor


def workspace(client, name):
    response = client.post("/v1/workspaces", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def customer(client, workspace_id, external_id="customer-42"):
    response = client.post(
        f"/v1/workspaces/{workspace_id}/customers",
        json={"name": "Affected customer", "external_id": external_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def investigation(client, workspace_id, customer_id):
    response = client.post(
        f"/v1/workspaces/{workspace_id}/investigations",
        json={"customer_id": customer_id, "question": "Why did exports fail?"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "queued"
    return response.json()["id"]


def test_owner_can_add_revoke_and_reactivate_teammate_without_changing_identity(actors):
    owner, teammate = actors("owner"), actors("teammate")
    wid = workspace(owner, "Team permissions")
    user_id = teammate.get("/v1/me").json()["id"]
    path = f"/v1/workspaces/{wid}/memberships"
    assert teammate.get(path).status_code == 404
    added = owner.post(path, json={"user_id": user_id})
    assert added.status_code == 201 and added.json()["role"] == "viewer"
    member_path = f"{path}/{added.json()['id']}"
    assert teammate.get(path).status_code == 200
    assert owner.post(path, json={"user_id": user_id}).status_code == 409
    assert owner.patch(member_path, json={"active": False}).status_code == 200
    assert teammate.get(path).status_code == 404
    assert teammate.get("/v1/workspaces").json()["items"] == []
    assert teammate.get("/v1/me").json()["id"] == user_id
    assert owner.post(path, json={"user_id": user_id}).status_code == 409
    restored = owner.patch(member_path, json={"active": True, "role": "support"})
    assert restored.status_code == 200 and restored.json()["id"] == added.json()["id"]
    assert teammate.get(path).status_code == 200


@pytest.mark.parametrize("role", ["viewer", "support", "admin"])
def test_only_owners_manage_memberships_even_when_signed_jwt_claims_owner(actors, role):
    owner, teammate, outsider = actors("owner"), actors("teammate"), actors("outsider")
    wid = workspace(owner, "Role matrix")
    path = f"/v1/workspaces/{wid}/memberships"
    user_id = teammate.get("/v1/me").json()["id"]
    other_id = outsider.get("/v1/me").json()["id"]
    added = owner.post(path, json={"user_id": user_id, "role": role}).json()
    assert teammate.get(path).status_code == 200
    assert teammate.post(path, json={"user_id": other_id}).status_code == 403
    assert teammate.patch(f"{path}/{added['id']}", json={"role": "owner"}).status_code == 403
    assert outsider.patch(f"{path}/{added['id']}", json={"active": False}).status_code == 404
    result = teammate.post(
        f"/v1/workspaces/{wid}/customers", json={"name": "Test", "external_id": "new"}
    )
    assert result.status_code == (403 if role == "viewer" else 201)
    result = teammate.post(
        f"/v1/workspaces/{wid}/integrations", json={"name": "Test", "kind": "demo"}
    )
    assert result.status_code == (201 if role == "admin" else 403)


def test_membership_changes_are_scoped_and_validate_explicit_values(actors, db_session):
    owner, teammate = actors("owner"), actors("teammate")
    a, b = workspace(owner, "A"), workspace(teammate, "B")
    path = f"/v1/workspaces/{a}/memberships"
    other_member = teammate.get(f"/v1/workspaces/{b}/memberships").json()["items"][0]
    assert owner.patch(f"{path}/{other_member['id']}", json={"active": False}).status_code == 404
    assert owner.post(path, json={"user_id": str(uuid4())}).status_code == 404
    foreign_user = User(auth_issuer="https://other.invalid", auth_subject="foreign")
    db_session.add(foreign_user)
    db_session.flush()
    assert owner.post(path, json={"user_id": str(foreign_user.id)}).status_code == 404
    owner_member = owner.get(path).json()["items"][0]
    for change in (
        {},
        {"active": None},
        {"role": None},
        {"active": "false"},
        {"user_id": str(uuid4())},
        {"role": "superadmin"},
    ):
        assert owner.patch(f"{path}/{owner_member['id']}", json=change).status_code == 422
    assert (
        owner.post(path, json={"user_id": other_member["user_id"], "workspace_id": b}).status_code
        == 422
    )


def test_last_active_owner_cannot_be_demoted_or_removed_and_transfer_is_possible(actors):
    first, second = actors("first"), actors("second")
    wid = workspace(first, "Ownership")
    path = f"/v1/workspaces/{wid}/memberships"
    first_member = first.get(path).json()["items"][0]
    first_path = f"{path}/{first_member['id']}"
    assert first.patch(first_path, json={"role": "viewer"}).status_code == 409
    assert first.patch(first_path, json={"active": False}).status_code == 409
    second_id = second.get("/v1/me").json()["id"]
    second_member = first.post(path, json={"user_id": second_id, "role": "owner"}).json()
    assert first.patch(first_path, json={"role": "viewer"}).status_code == 200
    assert first.patch(first_path, json={"role": "owner"}).status_code == 403
    assert second.patch(f"{path}/{second_member['id']}", json={"active": False}).status_code == 409
    assert second.patch(first_path, json={"role": "owner"}).status_code == 200


def test_revocation_blocks_populated_investigations_and_evidence_with_existing_jwt(
    actors, db_session
):
    owner, teammate = actors("owner"), actors("teammate")
    wid = workspace(owner, "Evidence isolation")
    cid = customer(owner, wid)
    iid = investigation(owner, wid, cid)
    db_session.add(
        Evidence(
            workspace_id=UUID(wid),
            investigation_id=UUID(iid),
            kind=EvidenceKind.CONFIG,
            title="Private flag",
            source_ref="demo/private/config",
            excerpt_redacted="disabled",
            observed_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    user_id = teammate.get("/v1/me").json()["id"]
    path = f"/v1/workspaces/{wid}/memberships"
    member = owner.post(path, json={"user_id": user_id}).json()
    evidence_path = f"/v1/workspaces/{wid}/investigations/{iid}/evidence"
    assert len(teammate.get(evidence_path).json()["items"]) == 1
    assert owner.patch(f"{path}/{member['id']}", json={"active": False}).status_code == 200
    for resource in (
        "memberships",
        "customers",
        "integrations",
        "investigations",
        f"investigations/{iid}",
        f"investigations/{iid}/jobs",
        f"investigations/{iid}/tool-calls",
        f"investigations/{iid}/evidence",
        f"investigations/{iid}/report",
    ):
        response = teammate.get(f"/v1/workspaces/{wid}/{resource}")
        assert response.status_code == 404 and "Private flag" not in response.text


def test_investigation_and_job_are_persisted_atomically_with_both_scopes(actors, db_session):
    alice = actors("alice")
    wid = workspace(alice, "Acme SaaS")
    cid = customer(alice, wid)
    iid = investigation(alice, wid, cid)
    row = db_session.get(Investigation, UUID(iid))
    jobs = list(db_session.scalars(select(Job).where(Job.investigation_id == UUID(iid))))
    assert row.workspace_id == UUID(wid) and row.customer_id == UUID(cid)
    assert len(jobs) == 1 and jobs[0].workspace_id == row.workspace_id
    assert (
        alice.get(f"/v1/workspaces/{wid}/investigations/{iid}/jobs").json()["items"][0]["state"]
        == "queued"
    )


def test_two_companies_cannot_read_or_attach_each_others_customers_and_cases(actors):
    alice, bob = actors("alice"), actors("bob")
    a, b = workspace(alice, "Acme"), workspace(bob, "Beta")
    ca, cb = customer(alice, a), customer(bob, b)
    ia, ib = investigation(alice, a, ca), investigation(bob, b, cb)
    assert len(alice.get("/v1/workspaces").json()["items"]) == 1
    assert alice.get(f"/v1/workspaces/{b}/customers").status_code == 404
    assert alice.get(f"/v1/workspaces/{a}/customers/{cb}").status_code == 404
    assert alice.get(f"/v1/workspaces/{a}/investigations/{ib}").status_code == 404
    assert bob.get(f"/v1/workspaces/{a}/investigations/{ia}/evidence").status_code == 404
    response = alice.post(
        f"/v1/workspaces/{a}/investigations",
        json={"customer_id": cb, "question": "Why did exports fail?"},
    )
    assert response.status_code == 404


def test_same_external_customer_id_is_allowed_across_companies_but_not_duplicated_within_one(
    actors,
):
    alice, bob = actors("alice"), actors("bob")
    a, b = workspace(alice, "Acme"), workspace(bob, "Beta")
    customer(alice, a)
    customer(bob, b)
    response = alice.post(
        f"/v1/workspaces/{a}/customers", json={"name": "Duplicate", "external_id": "customer-42"}
    )
    assert response.status_code == 409
    assert "customer-42" not in response.text


def test_database_itself_rejects_cross_company_customer_even_without_api(actors, db_session):
    alice, bob = actors("alice"), actors("bob")
    a, b = workspace(alice, "Acme"), workspace(bob, "Beta")
    cb = customer(bob, b)
    membership = db_session.scalar(select(Membership).where(Membership.workspace_id == UUID(a)))
    db_session.add(
        Investigation(
            workspace_id=UUID(a),
            customer_id=UUID(cb),
            created_by_user_id=membership.user_id,
            question="Invalid scope",
        )
    )
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23503"


def test_database_rejects_job_attached_to_another_company(actors, db_session):
    alice, bob = actors("alice"), actors("bob")
    a, b = workspace(alice, "Acme"), workspace(bob, "Beta")
    cb = customer(bob, b)
    ib = investigation(bob, b, cb)
    job = db_session.scalar(select(Job).where(Job.investigation_id == UUID(ib)))
    job.workspace_id = UUID(a)
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23503"


def test_database_membership_is_authoritative_and_revocation_takes_effect(actors, db_session):
    alice = actors("alice")
    a = workspace(alice, "Acme")
    ca = customer(alice, a)
    membership = db_session.scalar(select(Membership).where(Membership.workspace_id == UUID(a)))
    membership.role = MembershipRole.VIEWER
    db_session.commit()
    assert alice.get(f"/v1/workspaces/{a}/customers").status_code == 200
    assert (
        alice.post(
            f"/v1/workspaces/{a}/investigations",
            json={"customer_id": ca, "question": "Why did exports fail?"},
        ).status_code
        == 403
    )
    membership.active = False
    db_session.commit()
    assert alice.get(f"/v1/workspaces/{a}/customers").status_code == 404


def test_citations_are_scoped_to_the_case_in_service_and_database(actors, db_session):
    alice = actors("alice")
    a = workspace(alice, "Acme")
    c1, c2 = customer(alice, a, "one"), customer(alice, a, "two")
    i1, i2 = investigation(alice, a, c1), investigation(alice, a, c2)
    evidence = Evidence(
        workspace_id=UUID(a),
        investigation_id=UUID(i2),
        kind=EvidenceKind.CONFIG,
        title="Config",
        source_ref="demo/config/version-1",
        excerpt_redacted="Disabled",
        observed_at=datetime.now(UTC),
    )
    db_session.add(evidence)
    db_session.flush()
    row = db_session.get(Investigation, UUID(i1))
    draft = ReportDraft(
        summary="Export disabled",
        root_cause="Disabled by configuration",
        confidence=0.9,
        citations=[{"evidence_id": evidence.id}],
    )
    with pytest.raises(ValueError, match="Citations must belong"):
        save_report(db_session, row, draft)
    report = Report(
        workspace_id=UUID(a), investigation_id=UUID(i1), summary="No valid evidence", confidence=0
    )
    db_session.add(report)
    db_session.flush()
    db_session.add(
        ReportCitation(
            workspace_id=UUID(a),
            investigation_id=UUID(i1),
            report_id=report.id,
            evidence_id=evidence.id,
        )
    )
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23503"


def test_report_and_feedback_use_only_matching_evidence_and_authenticated_author(
    actors, db_session
):
    alice = actors("alice")
    a = workspace(alice, "Acme")
    ca = customer(alice, a)
    iid = investigation(alice, a, ca)
    row = db_session.get(Investigation, UUID(iid))
    transition_investigation(row, InvestigationState.RUNNING)
    evidence = Evidence(
        workspace_id=UUID(a),
        investigation_id=row.id,
        kind=EvidenceKind.CONFIG,
        title="Export flag",
        source_ref="demo/account/config",
        excerpt_redacted="False",
        observed_at=datetime.now(UTC),
    )
    db_session.add(evidence)
    db_session.flush()
    report = save_report(
        db_session,
        row,
        ReportDraft(
            summary="Exports disabled",
            root_cause="Flag false",
            confidence=0.9,
            citations=[{"evidence_id": evidence.id}],
        ),
    )
    transition_investigation(row, InvestigationState.COMPLETED)
    db_session.commit()
    result = alice.get(f"/v1/workspaces/{a}/investigations/{iid}/report")
    assert result.status_code == 200, result.text
    assert result.json()["citations"][0]["evidence_id"] == str(evidence.id)
    path = f"/v1/workspaces/{a}/investigations/{iid}/reports/{report.id}/feedback"
    assert alice.post(path, json={"rating": "helpful", "user_id": str(uuid4())}).status_code == 422
    feedback = alice.post(path, json={"rating": "helpful"})
    user = db_session.scalar(select(User).where(User.auth_subject == "alice"))
    assert feedback.status_code == 201 and feedback.json()["user_id"] == str(user.id)


@pytest.mark.parametrize(
    "terminal",
    [InvestigationState.COMPLETED, InvestigationState.INCONCLUSIVE, InvestigationState.FAILED],
)
def test_state_transitions_have_timestamps_and_terminal_states_cannot_restart(
    actors, db_session, terminal
):
    alice = actors("alice")
    a = workspace(alice, "Acme")
    ca = customer(alice, a)
    iid = investigation(alice, a, ca)
    row = db_session.get(Investigation, UUID(iid))
    transition_investigation(row, InvestigationState.RUNNING)
    transition_investigation(row, terminal)
    db_session.flush()
    assert row.started_at is not None and row.finished_at >= row.started_at
    with pytest.raises(ValueError, match="Invalid investigation"):
        transition_investigation(row, InvestigationState.RUNNING)


def test_database_rejects_completed_state_without_execution_timestamps(actors, db_session):
    alice = actors("alice")
    a = workspace(alice, "Acme")
    ca = customer(alice, a)
    iid = investigation(alice, a, ca)
    row = db_session.get(Investigation, UUID(iid))
    row.state = InvestigationState.COMPLETED
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23514"


def test_integrations_do_not_accept_or_expose_secret_references(actors, db_session):
    from backend.app.models import Integration

    alice = actors("alice")
    wid = workspace(alice, "Acme")
    path = f"/v1/workspaces/{wid}/integrations"
    assert (
        alice.post(path, json={"name": "Demo", "kind": "demo", "secret_ref": "forged"}).status_code
        == 422
    )
    result = alice.post(path, json={"name": "Demo", "kind": "demo"})
    assert result.status_code == 201 and result.json()["enabled"] is False
    row = db_session.get(Integration, UUID(result.json()["id"]))
    row.secret_ref = "synthetic-private-secret-reference"
    db_session.commit()
    assert "synthetic-private-secret-reference" not in alice.get(path).text


def test_database_rejects_non_read_only_tool_calls(actors, db_session):
    from backend.app.domain import ToolCallState
    from backend.app.models import ToolCall

    alice = actors("alice")
    wid = workspace(alice, "Acme")
    cid = customer(alice, wid)
    iid = investigation(alice, wid, cid)
    job = db_session.scalar(select(Job).where(Job.investigation_id == UUID(iid)))
    db_session.add(
        ToolCall(
            workspace_id=UUID(wid),
            investigation_id=UUID(iid),
            job_id=job.id,
            tool_name="unsafe-action",
            state=ToolCallState.RUNNING,
            read_only=False,
        )
    )
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23514"


def test_database_rejects_invalid_report_confidence(actors, db_session):
    alice = actors("alice")
    wid = workspace(alice, "Acme")
    cid = customer(alice, wid)
    iid = investigation(alice, wid, cid)
    db_session.add(
        Report(
            workspace_id=UUID(wid),
            investigation_id=UUID(iid),
            summary="Invalid score",
            confidence=1.5,
        )
    )
    with pytest.raises(IntegrityError) as error:
        db_session.flush()
    assert error.value.orig.sqlstate == "23514"
