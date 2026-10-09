from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings

bearer = HTTPBearer(auto_error=False)
ALGORITHMS = ("EdDSA", "RS256", "ES256")


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str


class TokenVerifier:
    def __init__(self, settings: Settings):
        self.issuer = settings.effective_issuer
        self.audience = settings.auth_audience
        self.jwks = (
            jwt.PyJWKClient(settings.jwks_url.get_secret_value(), timeout=5, lifespan=300)
            if settings.jwks_url
            else None
        )

    def verify(self, token: str) -> Principal:
        if not self.issuer or self.jwks is None:
            raise HTTPException(503, "Authentication is not configured.")
        try:
            if len(token) > 8192:
                raise jwt.InvalidTokenError()
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ALGORITHMS or not isinstance(header.get("kid"), str):
                raise jwt.InvalidTokenError()
            if not 1 <= len(header["kid"]) <= 256:
                raise jwt.InvalidTokenError()
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            if header["alg"] != signing_key.algorithm_name:
                raise jwt.InvalidTokenError()
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[signing_key.algorithm_name],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "require": ["exp", "iat", "iss", "sub"],
                    "verify_aud": self.audience is not None,
                },
                leeway=5,
            )
            subject = claims["sub"]
            if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
                raise jwt.InvalidTokenError()
            return Principal(issuer=self.issuer, subject=subject)
        except jwt.PyJWKClientConnectionError:
            raise HTTPException(503, "Authentication provider is unavailable.") from None
        except (jwt.PyJWTError, ValueError):
            raise HTTPException(
                401, "Invalid authentication token.", headers={"WWW-Authenticate": "Bearer"}
            ) from None


def require_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None:
        raise HTTPException(
            401, "Authentication is required.", headers={"WWW-Authenticate": "Bearer"}
        )
    return request.app.state.token_verifier.verify(credentials.credentials)
