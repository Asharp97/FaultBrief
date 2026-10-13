from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..config import REPOSITORY_ROOT


class DiagnosticSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / ".env", REPOSITORY_ROOT / "backend" / ".env"),
        env_prefix="DIAGNOSTIC_",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
        hide_input_in_errors=True,
    )
    environment: Literal["development", "test", "production"] = Field(
        default="development", validation_alias="FAULTBRIEF_ENVIRONMENT"
    )
    demo_url: str = "http://127.0.0.1:8001"
    demo_token: SecretStr | None = None
    bindings_path: Path = REPOSITORY_ROOT / ".tools" / "diagnostics" / "bindings.json"
    runbooks_path: Path = REPOSITORY_ROOT / "backend" / "runbooks" / "ledger.json"
    max_records: int = Field(default=20, ge=1, le=50)
    max_response_bytes: int = Field(default=65536, ge=1024, le=262144)
    request_timeout_seconds: float = Field(default=3, gt=0, le=10)
    total_timeout_seconds: float = Field(default=20, gt=0, le=45)
    max_requests: int = Field(default=6, ge=1, le=10)

    @field_validator("demo_token")
    @classmethod
    def credential_length(cls, value):
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("A diagnostic credential must contain at least 32 characters.")
        return value

    @field_validator("demo_url")
    @classmethod
    def trusted_endpoint(cls, value, info):
        url = urlsplit(value)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
            or url.scheme not in {"http", "https"}
            or (
                url.scheme == "http" and (not local or info.data.get("environment") == "production")
            )
        ):
            raise ValueError("Use HTTPS, or a loopback HTTP endpoint during development.")
        return value.rstrip("/")
