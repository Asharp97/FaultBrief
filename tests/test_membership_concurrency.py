from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Membership, User, Workspace


def test_concurrent_owner_removal_preserves_one_active_owner(postgres_engine):
    issuer = "https://auth.example.invalid"
    subjects = [f"concurrent-{uuid4()}" for _ in range(2)]
    app = create_app(
        Settings(_env_file=None, auth_url=f"{issuer}/neondb/auth", jwks_url=f"{issuer}/jwks"),
        engine=postgres_engine,
    )
    key = Ed25519PrivateKey.generate()
    app.state.token_verifier.jwks.get_signing_key_from_jwt = lambda _token: SimpleNamespace(
        key=key.public_key(), algorithm_name="EdDSA"
    )
    now = datetime.now(UTC)
    clients = [
        TestClient(
            app,
            headers={
                "Authorization": "Bearer "
                + jwt.encode(
                    {"iss": issuer, "sub": subject, "iat": now, "exp": now + timedelta(minutes=5)},
                    key,
                    algorithm="EdDSA",
                    headers={"kid": "test-key"},
                )
            },
        )
        for subject in subjects
    ]
    try:
        first, second = clients
        wid = first.post("/v1/workspaces", json={"name": "Concurrent owner guard"}).json()["id"]
        path = f"/v1/workspaces/{wid}/memberships"
        first_member = first.get(path).json()["items"][0]
        second_user = second.get("/v1/me").json()["id"]
        response = first.post(path, json={"user_id": second_user, "role": "owner"})
        assert response.status_code == 201
        second_member = response.json()
        barrier = Barrier(2)

        def remove(client, member):
            barrier.wait(timeout=5)
            return client.patch(f"{path}/{member['id']}", json={"active": False}).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(remove, first, first_member),
                executor.submit(remove, second, second_member),
            ]
            assert sorted(future.result(timeout=15) for future in futures) == [200, 409]
        with Session(postgres_engine) as session:
            owners = list(
                session.scalars(
                    select(Membership).where(
                        Membership.workspace_id == UUID(wid),
                        Membership.active.is_(True),
                        Membership.role == "owner",
                    )
                )
            )
            assert len(owners) == 1
    finally:
        for client in clients:
            client.close()
        # This test uses committed transactions to exercise real concurrent connections.
        # Delete only its randomly identified, otherwise empty test workspaces/accounts.
        with postgres_engine.begin() as connection:
            user_filter = (User.auth_issuer == issuer) & User.auth_subject.in_(subjects)
            workspace_ids = list(
                connection.scalars(select(Membership.workspace_id).join(User).where(user_filter))
            )
            if workspace_ids:
                connection.execute(
                    delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
                )
                connection.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
            connection.execute(delete(User).where(user_filter))
