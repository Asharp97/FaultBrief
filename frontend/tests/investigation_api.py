"""Loopback-only integration harness: real API/worker, disposable PostgreSQL, synthetic model."""

import json
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import mkdtemp
from typing import Annotated, Literal
from uuid import UUID

import httpx2
import jwt
from alembic import command
from alembic.config import Config
from fastapi import Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.auth import Principal, require_principal
from backend.app.config import Settings
from backend.app.database import database_engine, get_session
from backend.app.diagnostics.cli import connect
from backend.app.diagnostics.config import DiagnosticSettings
from backend.app.investigations.config import InvestigationSettings
from backend.app.investigations.worker import Worker
from backend.app.main import create_app
from backend.app.services import require_owner_workspace, workspace_membership

ROOT = Path(__file__).resolve().parents[2]
url = os.environ.get("FAULTBRIEF_TEST_DATABASE_URL", "")
parsed = make_url(url)
if parsed.host not in {"localhost", "127.0.0.1", "::1"} or not (parsed.database or "").endswith(
    "_test"
):
    raise RuntimeError("This harness requires a disposable loopback *_test database.")
engine = database_engine(url)
migration = Config(str(ROOT / "backend" / "alembic.ini"))
with engine.begin() as connection:
    migration.attributes["connection"] = connection
    command.upgrade(migration, "head")
settings = Settings(
    _env_file=None,
    faultbrief_environment="test",
    database_url=url,
    auth_url="https://auth.example.invalid/neondb/auth",
    jwks_url="https://auth.example.invalid/jwks",
    auth_issuer="http://127.0.0.1:58110",
)
app = create_app(settings, engine=engine)
app.state.token_verifier.jwks = jwt.PyJWKClient("http://127.0.0.1:58110/test/jwks")
diagnostics = DiagnosticSettings(
    _env_file=None,
    environment="test",
    demo_url="http://127.0.0.1:58112",
    demo_token="synthetic-demo-diagnostic-" + "d" * 32,
    bindings_path=Path(mkdtemp(prefix="faultbrief-e2e-bindings-")) / "bindings.json",
)


def model(request):
    context = json.loads(json.loads(request.content)["messages"][1]["content"])
    report = context["baseline"]
    report["summary"] = "AI explanation: " + report["summary"]
    return httpx2.Response(
        200,
        headers={"Content-Type": "application/json"},
        stream=httpx2.ByteStream(
            json.dumps(
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(report)}}
                    ],
                }
            ).encode()
        ),
    )


worker = Worker(
    engine,
    InvestigationSettings(
        _env_file=None,
        faultbrief_environment="test",
        model_provider="openai-compatible",
        model_name="synthetic-explainer",
        ai_provider_api_key="synthetic-model-key",
        model_endpoint="http://127.0.0.1:58113/test/model",
    ),
    diagnostics,
    model_transport=httpx2.MockTransport(model),
)
base_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application):
    stop = threading.Event()

    def run():
        while not stop.is_set():
            worker.run_once()
            stop.wait(0.2)

    thread = threading.Thread(target=run, name="synthetic-investigation-worker", daemon=True)
    async with base_lifespan(application):
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=5)
            engine.dispose()


app.router.lifespan_context = lifespan


class Seed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    scenario: Literal[
        "healthy", "permission_removed", "feature_disabled", "job_failed", "ambiguous"
    ]


@app.post("/test/seed", include_in_schema=False)
def seed(
    body: Seed,
    principal: Annotated[Principal, Depends(require_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    require_owner_workspace(session, principal, body.workspace_id)
    owner = workspace_membership(session, principal, body.workspace_id)
    with httpx2.Client(trust_env=False, timeout=5) as client:
        result = client.post(
            "http://127.0.0.1:58112/lab/runs",
            json={"scenario": body.scenario},
            headers={"Authorization": "Bearer synthetic-demo-operator-" + "o" * 32},
        )
        result.raise_for_status()
    source = result.json()
    binding = connect(
        session, diagnostics, body.workspace_id, owner.user_id, UUID(source["customer_id"])
    )
    return {
        "customer_id": str(binding.customer_id),
        "member_id": source["member_id"],
        "request_id": source["probe"]["request_id"],
        "job_id": source["probe"]["job_id"],
    }
