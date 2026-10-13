from urllib.parse import urlsplit

from pydantic import Field, field_validator

from ..config import Settings


class InvestigationSettings(Settings):
    model_endpoint: str = "https://api.openai.com/v1/chat/completions"
    model_timeout_seconds: float = Field(default=15, gt=0, le=30)
    model_max_completion_tokens: int = Field(default=1600, ge=200, le=3000)
    model_max_context_chars: int = Field(default=12000, ge=1000, le=24000)
    worker_lease_seconds: int = Field(default=120, ge=90, le=600)
    worker_poll_seconds: float = Field(default=5, ge=1, le=60)

    @field_validator("model_endpoint")
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
            or url.scheme not in {"http", "https"}
            or (
                url.scheme == "http"
                and (not local or info.data.get("faultbrief_environment") == "production")
            )
        ):
            raise ValueError("Use an HTTPS model endpoint, or loopback HTTP during development.")
        return value
