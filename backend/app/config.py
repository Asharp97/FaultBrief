from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / ".env", REPOSITORY_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        populate_by_name=True,
        hide_input_in_errors=True,
        extra="ignore",
    )

    faultbrief_environment: Literal["development", "test", "production"] = "development"
    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    demo_service_url: str = "http://127.0.0.1:8001"
    database_url: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("DATABASE_URL", "DB_URL")
    )
    migration_database_url: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("MIGRATION_DATABASE_URL", "DATABASE_URL_UNPOOLED"),
    )
    auth_url: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("AUTH_URL", "NEON_AUTH_BASE_URL")
    )
    jwks_url: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("JWKS_URL", "NEON_AUTH_JWKS_URL")
    )
    auth_issuer: str | None = None
    auth_audience: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    ai_provider_api_key: SecretStr | None = None

    @field_validator("auth_url", "jwks_url")
    @classmethod
    def https_endpoint(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            url = urlsplit(value.get_secret_value())
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Auth endpoints must be HTTPS URLs without embedded credentials.")
        return value

    @property
    def effective_issuer(self) -> str | None:
        if self.auth_issuer:
            return self.auth_issuer
        if self.auth_url:
            url = urlsplit(self.auth_url.get_secret_value())
            return f"{url.scheme}://{url.netloc}"
        return None
