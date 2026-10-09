import hmac
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from .config import DemoSettings
from .schemas import (
    CustomerRead,
    CustomerSummary,
    Items,
    JobRead,
    LogsPage,
    MemberRead,
    Page,
    ReportRead,
)
from .store import SCENARIOS, DemoStore, ExportRejected, MissingRecord

bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10000)]


class ExportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: UUID
    report_id: UUID


class ScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal[
        "healthy", "permission_removed", "feature_disabled", "job_failed", "ambiguous"
    ]


def create_app(settings: DemoSettings | None = None):
    settings = settings or DemoSettings()
    store = DemoStore(settings.database_path)

    @asynccontextmanager
    async def lifespan(_app):
        store.initialize()
        yield

    app = FastAPI(title="FaultBrief Reporting Demo", version="0.2.0", lifespan=lifespan)
    app.state.store = store

    def identity(credentials: Credentials):
        if credentials is None:
            raise HTTPException(
                401, "Demo access token required.", headers={"WWW-Authenticate": "Bearer"}
            )
        for role, key in (
            ("operator", settings.operator_token),
            ("app", settings.app_token),
            ("diagnostic", settings.diagnostic_token),
        ):
            if key and hmac.compare_digest(
                credentials.credentials.encode(), key.get_secret_value().encode()
            ):
                return role
        raise HTTPException(401, "Invalid demo access token.")

    def application_access(role: Annotated[str, Depends(identity)]):
        if role not in {"operator", "app"}:
            raise HTTPException(403, "Diagnostic access is read-only.")

    def operator_access(role: Annotated[str, Depends(identity)]):
        if role != "operator":
            raise HTTPException(403, "Lab operator access required.")
        if settings.environment == "production":
            raise HTTPException(403, "Lab controls are disabled in production.")

    ReadAccess = Depends(identity)
    AppAccess = Depends(application_access)
    LabAccess = Depends(operator_access)

    @app.exception_handler(sqlite3.Error)
    def unavailable(_request: Request, _error: sqlite3.Error):
        return JSONResponse({"detail": "Demo storage is unavailable."}, status_code=503)

    @app.exception_handler(MissingRecord)
    def missing(_request: Request, _error: MissingRecord):
        return JSONResponse({"detail": "Record not found in this customer scope."}, status_code=404)

    @app.exception_handler(ExportRejected)
    def rejected(_request: Request, error: ExportRejected):
        return JSONResponse(
            {"detail": error.detail, "request_id": error.request_id}, status_code=error.status
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "faultbrief-demo"}

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(Path(__file__).resolve().parents[1] / "static" / "index.html")

    @app.get("/v1/customers", response_model=Page[CustomerSummary], dependencies=[ReadAccess])
    def customers(limit: Limit = 50, offset: Offset = 0):
        return {"items": store.customers(limit, offset), "limit": limit, "offset": offset}

    @app.get("/v1/customers/{customer_id}", response_model=CustomerRead, dependencies=[ReadAccess])
    def customer(customer_id: UUID):
        return store.customer(str(customer_id))

    @app.get(
        "/v1/customers/{customer_id}/members",
        response_model=Items[MemberRead],
        dependencies=[ReadAccess],
    )
    def members(customer_id: UUID):
        return {"items": store.members(str(customer_id))}

    @app.get(
        "/v1/customers/{customer_id}/reports",
        response_model=Items[ReportRead],
        dependencies=[ReadAccess],
    )
    def reports(customer_id: UUID):
        return {"items": store.reports(str(customer_id))}

    @app.post(
        "/v1/customers/{customer_id}/exports",
        response_model=JobRead,
        dependencies=[AppAccess],
        status_code=202,
    )
    def export(customer_id: UUID, body: ExportCreate, tasks: BackgroundTasks):
        job = store.create_export(str(customer_id), str(body.member_id), str(body.report_id))
        tasks.add_task(store.finish_export, job["id"])
        return job

    @app.get(
        "/v1/customers/{customer_id}/jobs", response_model=Page[JobRead], dependencies=[ReadAccess]
    )
    def jobs(customer_id: UUID, limit: Limit = 50, offset: Offset = 0):
        return {
            "items": store.jobs(str(customer_id), limit, offset),
            "limit": limit,
            "offset": offset,
        }

    @app.get(
        "/v1/customers/{customer_id}/jobs/{job_id}",
        response_model=JobRead,
        dependencies=[ReadAccess],
    )
    def job(customer_id: UUID, job_id: UUID):
        return store.job(str(customer_id), str(job_id))

    @app.get("/v1/customers/{customer_id}/jobs/{job_id}/download", dependencies=[AppAccess])
    def download(customer_id: UUID, job_id: UUID, member_id: UUID):
        return Response(
            store.download(str(customer_id), str(job_id), str(member_id)),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="revenue-export.csv"'},
        )

    @app.get("/v1/customers/{customer_id}/logs", response_model=LogsPage, dependencies=[ReadAccess])
    def logs(
        customer_id: UUID, limit: Limit = 50, offset: Offset = 0, request_id: UUID | None = None
    ):
        return store.logs(str(customer_id), limit, offset, str(request_id) if request_id else None)

    # Operator routes are hidden from the investigator's public API contract.
    @app.get("/lab/scenarios", dependencies=[LabAccess], include_in_schema=False)
    def scenarios():
        return {"items": SCENARIOS}

    @app.post("/lab/runs", dependencies=[LabAccess], include_in_schema=False, status_code=201)
    def create_run(body: ScenarioCreate):
        return store.create_run(body.scenario)

    @app.post("/lab/runs/{run_id}/reset", dependencies=[LabAccess], include_in_schema=False)
    def reset(run_id: UUID):
        return store.reset(str(run_id))

    app.mount(
        "/assets",
        StaticFiles(directory=Path(__file__).resolve().parents[1] / "static"),
        name="assets",
    )
    return app


app = create_app()
