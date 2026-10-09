from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.auth import Principal, TokenVerifier
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.schemas import InvestigationCreate, ReportDraft

ISSUER = "https://auth.example.invalid"


@pytest.fixture
def signed_identity():
    key = Ed25519PrivateKey.generate()
    settings = Settings(_env_file=None, auth_url=f"{ISSUER}/neondb/auth", jwks_url=f"{ISSUER}/jwks")
    verifier = TokenVerifier(settings)
    verifier.jwks.get_signing_key_from_jwt = lambda _token: SimpleNamespace(
        key=key.public_key(), algorithm_name="EdDSA"
    )

    def token(**overrides):
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iss": ISSUER,
                "sub": "alice",
                "iat": now,
                "exp": now + timedelta(minutes=5),
                **overrides,
            },
            key,
            algorithm="EdDSA",
            headers={"kid": "test-key"},
        )

    return verifier, token


def test_valid_signature_is_required_and_only_issuer_subject_are_trusted(signed_identity):
    verifier, token = signed_identity
    assert verifier.verify(token(role="owner", workspace_id=str(uuid4()))) == Principal(
        ISSUER, "alice"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://other.example.invalid"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"iat": datetime.now(UTC) + timedelta(minutes=1)},
        {"sub": ""},
    ],
)
def test_wrong_issuer_expiry_future_issue_time_and_empty_subject_are_rejected(
    signed_identity, overrides
):
    verifier, token = signed_identity
    with pytest.raises(HTTPException) as error:
        verifier.verify(token(**overrides))
    assert error.value.status_code == 401


def test_wrong_signing_key_and_symmetric_algorithm_are_rejected(signed_identity):
    verifier, token = signed_identity
    decoded = jwt.decode(token(), options={"verify_signature": False})
    other = jwt.encode(
        decoded, Ed25519PrivateKey.generate(), algorithm="EdDSA", headers={"kid": "test-key"}
    )
    for invalid in [
        other,
        jwt.encode(
            decoded,
            "synthetic-test-secret-longer-than-thirty-two-bytes",
            algorithm="HS256",
            headers={"kid": "test-key"},
        ),
        "not-a-token",
    ]:
        with pytest.raises(HTTPException) as error:
            verifier.verify(invalid)
        assert error.value.status_code == 401


def test_missing_expiration_is_rejected(signed_identity):
    verifier, token = signed_identity
    with pytest.raises(HTTPException) as error:
        verifier.verify(token(exp=None))
    assert error.value.status_code == 401


def test_missing_bearer_is_unauthorized_without_opening_database():
    client = TestClient(create_app(Settings(_env_file=None)))
    assert client.get("/v1/workspaces").status_code == 401


def test_body_cannot_override_scope_creator_or_investigation_state():
    for field in ["workspace_id", "created_by_user_id", "state"]:
        with pytest.raises(ValidationError):
            InvestigationCreate(
                customer_id=uuid4(), question="Why did this export fail?", **{field: "forged"}
            )


def test_report_requires_citations_for_root_cause_and_finite_bounded_confidence():
    with pytest.raises(ValidationError):
        ReportDraft(summary="Failure found", root_cause="Export disabled", confidence=0.9)
    for confidence in [float("nan"), float("inf"), -0.1, 1.1]:
        with pytest.raises(ValidationError):
            ReportDraft(summary="Insufficient evidence", confidence=confidence)


def test_backend_env_aliases_are_loaded_and_secret_values_are_masked(tmp_path, monkeypatch):
    for name in ["DATABASE_URL", "DB_URL", "AUTH_URL", "JWKS_URL"]:
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "DB_URL=postgresql://fake:private-password@example.invalid/example\n"
        "AUTH_URL=https://auth.example.invalid/neondb/auth\n"
        "JWKS_URL=https://auth.example.invalid/jwks\n"
    )
    settings = Settings(_env_file=env)
    assert settings.database_url is not None
    assert settings.effective_issuer == ISSUER
    assert "private-password" not in repr(settings)


def test_algorithm_cannot_be_changed_to_a_different_asymmetric_key_type(signed_identity):
    import json

    verifier, token = signed_identity
    parts = token().split(".")
    parts[0] = jwt.utils.base64url_encode(
        json.dumps({"alg": "RS256", "kid": "test-key"}).encode()
    ).decode()
    with pytest.raises(HTTPException) as error:
        verifier.verify(".".join(parts))
    assert error.value.status_code == 401


def test_configured_audience_is_enforced(signed_identity):
    verifier, token = signed_identity
    verifier.audience = "faultbrief"
    assert verifier.verify(token(aud="faultbrief")).subject == "alice"
    with pytest.raises(HTTPException) as error:
        verifier.verify(token(aud="another-service"))
    assert error.value.status_code == 401


def test_provider_outage_returns_generic_unavailable_error(signed_identity):
    verifier, token = signed_identity

    def unavailable(_token):
        raise jwt.PyJWKClientConnectionError("synthetic-private-provider-detail")

    verifier.jwks.get_signing_key_from_jwt = unavailable
    with pytest.raises(HTTPException) as error:
        verifier.verify(token())
    assert error.value.status_code == 503
    assert "synthetic-private-provider-detail" not in error.value.detail
