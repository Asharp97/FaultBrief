"""Local operator setup; never imported by the diagnostic service or investigator."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx2
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.database import database_engine
from backend.app.diagnostics.bindings import DiagnosticError
from backend.app.diagnostics.cli import connect
from backend.app.diagnostics.config import DiagnosticSettings
from backend.app.domain import MembershipRole
from backend.app.models import Membership
from demo.app.config import DemoSettings
from demo.evaluation.control import ANSWERS, record_answer

ROOT = Path(__file__).resolve().parents[2]


def prepare(
    session,
    diagnostics,
    demo,
    workspace_id,
    owner_user_id,
    scenario="feature_disabled",
    *,
    transport=None,
    answer_path=None,
):
    url = urlsplit(diagnostics.demo_url)
    if (
        diagnostics.environment == "production"
        or demo.environment == "production"
        or url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or url.scheme not in {"http", "https"}
        or url.username
        or url.password
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
    ):
        raise DiagnosticError("local_demo_required")
    if scenario not in ANSWERS:
        raise DiagnosticError("unknown_demo_scenario")
    if not demo.operator_token or not demo.diagnostic_token or not diagnostics.demo_token:
        raise DiagnosticError("demo_credentials_not_configured")
    if demo.diagnostic_token.get_secret_value() != diagnostics.demo_token.get_secret_value():
        raise DiagnosticError("diagnostic_key_mismatch")
    owner = session.scalar(
        select(Membership.id).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == owner_user_id,
            Membership.active.is_(True),
            Membership.role == MembershipRole.OWNER,
        )
    )
    if owner is None:
        raise DiagnosticError("workspace_owner_not_found")
    try:
        with httpx2.Client(trust_env=False, follow_redirects=False, transport=transport) as client:
            with client.stream(
                "POST",
                diagnostics.demo_url + "/lab/runs",
                json={"scenario": scenario},
                timeout=5,
                headers={
                    "Authorization": "Bearer " + demo.operator_token.get_secret_value(),
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                if (
                    response.status_code != 201
                    or "application/json" not in response.headers.get("content-type", "")
                    or response.headers.get("content-encoding", "identity") != "identity"
                ):
                    raise DiagnosticError("demo_setup_unavailable")
                data = bytearray()
                for chunk in response.iter_raw(chunk_size=8192):
                    data.extend(chunk)
                    if len(data) > 32768:
                        raise DiagnosticError("invalid_demo_response")
                run = json.loads(data)
        source_id, member_id, request_id = (
            UUID(run["customer_id"]),
            UUID(run["member_id"]),
            UUID(run["probe"]["request_id"]),
        )
        run_id = UUID(run["run_id"])
        job_id = UUID(run["probe"]["job_id"]) if run["probe"].get("job_id") else None
        record_answer(
            run, scenario, answer_path or ROOT / "training/data/private/demo-answer-key.jsonl"
        )
    except (httpx2.HTTPError, ValueError, TypeError, KeyError, OSError):
        raise DiagnosticError("demo_setup_unavailable") from None
    binding = connect(
        session, diagnostics, workspace_id, owner_user_id, source_id, transport=transport
    )
    return {
        "status": "connected",
        "workspace_id": str(workspace_id),
        "customer_id": str(binding.customer_id),
        "source_customer_id": str(source_id),
        "run_id": str(run_id),
        "question": "Why did this customer's revenue export fail?",
        "context": {
            "member_id": str(member_id),
            "request_id": str(request_id),
            **({"job_id": str(job_id)} if job_id else {}),
        },
        "next_step": "In FaultBrief, click Refresh customers, select the new account, "
        "and submit the question. Request references are optional.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Create a local Ledger sample and connect it to an existing workspace. "
        "No model or ticket is submitted."
    )
    parser.add_argument("--workspace-id", required=True, type=UUID)
    parser.add_argument("--owner-user-id", required=True, type=UUID)
    parser.add_argument("--scenario", choices=list(ANSWERS), default="feature_disabled")
    parser.add_argument(
        "--base-url", help="Loopback Ledger URL, if the development launcher uses a custom port."
    )
    args = parser.parse_args()
    engine = None
    try:
        settings, demo = Settings(), DemoSettings()
        diagnostics = DiagnosticSettings(**({"demo_url": args.base_url} if args.base_url else {}))
        if not settings.database_url:
            raise DiagnosticError("database_not_configured")
        engine = database_engine(settings.database_url.get_secret_value())
        with Session(engine, expire_on_commit=False) as session:
            result = prepare(
                session, diagnostics, demo, args.workspace_id, args.owner_user_id, args.scenario
            )
        print(json.dumps(result, indent=2))
    except DiagnosticError as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": error.code,
                    "help": "Check workspace ownership, start Ledger, and configure the matching "
                    "diagnostic key. See docs/testing-first-investigation.md.",
                }
            )
        )
        raise SystemExit(1) from None
    except (SQLAlchemyError, ValidationError, OSError):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": "setup_unavailable",
                    "help": "Check local configuration and run pnpm run db:migrate "
                    "before retrying.",
                }
            )
        )
        raise SystemExit(1) from None
    finally:
        if engine:
            engine.dispose()


if __name__ == "__main__":
    main()
