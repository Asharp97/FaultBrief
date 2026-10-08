from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    application = FastAPI(
        title="FaultBrief API",
        version="0.1.0",
        description=(
            "API foundation. Live investigations and authentication are not implemented yet."
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "faultbrief-api"}

    return application


app = create_app()
