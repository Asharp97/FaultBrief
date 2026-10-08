from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    faultbrief_environment: Literal["development", "test", "production"] = "development"
    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    demo_service_url: str = "http://127.0.0.1:8001"
    database_url: SecretStr | None = None
    model_provider: str | None = None
    model_name: str | None = None
    ai_provider_api_key: SecretStr | None = None
