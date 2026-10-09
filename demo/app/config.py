from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class DemoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / "demo" / ".env",
        env_prefix="DEMO_",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )
    environment: Literal["development", "test", "production"] = "development"
    database_path: Path = ROOT / ".tools" / "demo" / "reporting.sqlite3"
    operator_token: SecretStr | None = None
    app_token: SecretStr | None = None
    diagnostic_token: SecretStr | None = None

    @model_validator(mode="after")
    def separate_keys(self):
        keys = [
            key.get_secret_value()
            for key in (self.operator_token, self.app_token, self.diagnostic_token)
            if key
        ]
        if any(len(key) < 32 for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("Configured demo keys must be distinct and at least 32 characters.")
        return self
