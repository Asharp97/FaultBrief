from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from .auth import TokenVerifier
from .config import Settings
from .database import database_engine
from .routes import router


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings()
    owned_engine = engine is None
    if engine is None and settings.database_url:
        engine = database_engine(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        if owned_engine and application.state.database_engine is not None:
            application.state.database_engine.dispose()

    application = FastAPI(
        title="FaultBrief API",
        version="0.2.0",
        lifespan=lifespan,
        description="Scoped workspace/customer API. Investigations queue jobs; "
        "browser authentication uses the Neon SDK; the investigation worker arrives later.",
    )
    application.state.database_engine = engine
    application.state.token_verifier = TokenVerifier(settings)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(router)

    @application.exception_handler(IntegrityError)
    def conflict(_request: Request, _error: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": "Resource or relationship conflict."}
        )

    @application.exception_handler(OperationalError)
    @application.exception_handler(ProgrammingError)
    def unavailable(_request: Request, _error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": "Database is unavailable or unmigrated."}
        )

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "faultbrief-api"}

    return application


app = create_app()
