"""Operator-only evaluation preparation; the web service never imports this module."""

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from demo.app.config import DemoSettings

# Expected conclusions belong to the evaluator, not diagnostic HTTP responses.
ANSWERS = {
    "healthy": ("completed", None),
    "permission_removed": ("completed", "missing_export_permission"),
    "feature_disabled": ("completed", "exports_disabled"),
    "job_failed": ("completed", "artifact_write_failure"),
    "ambiguous": ("inconclusive", None),
}
ROOT = Path(__file__).resolve().parents[2]


def record_answer(run: dict, scenario: str, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    state, cause = ANSWERS[scenario]
    record = {
        "run_id": run["run_id"],
        "generation": run["generation"],
        "customer_id": run["customer_id"],
        "member_id": run["member_id"],
        "request_id": run["probe"]["request_id"],
        "expected_investigation_state": state,
        "expected_root_cause": cause,
    }
    with destination.open("a", encoding="utf8") as file:
        file.write(json.dumps(record) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["create", "reset", "seed-all"])
    parser.add_argument("value", nargs="?")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if (
        url.hostname not in {"127.0.0.1", "localhost", "::1"}
        or url.scheme not in {"http", "https"}
        or url.username
        or url.password
    ):
        parser.exit(2, "Evaluation preparation requires a loopback demo URL.\n")
    settings = DemoSettings()
    if settings.environment == "production" or not settings.operator_token:
        parser.exit(2, "Configure the development operator token first.\n")
    if args.operation == "create" and args.value not in ANSWERS:
        parser.exit(
            2, "Choose healthy, permission_removed, feature_disabled, job_failed, or ambiguous.\n"
        )
    if args.operation == "reset":
        try:
            run_id = UUID(args.value or "")
        except ValueError:
            parser.exit(2, "Supply the UUID of the run to reset.\n")
    scenarios = (
        list(ANSWERS)
        if args.operation == "seed-all"
        else ["healthy" if args.operation == "reset" else args.value]
    )
    output = []
    try:
        for scenario in scenarios:
            path = f"/lab/runs/{run_id}/reset" if args.operation == "reset" else "/lab/runs"
            body = {} if args.operation == "reset" else {"scenario": scenario}
            request = urllib.request.Request(
                args.base_url.rstrip("/") + path,
                data=json.dumps(body).encode(),
                method="POST",
                headers={
                    "Authorization": "Bearer " + settings.operator_token.get_secret_value(),
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                run = json.load(response)
            record_answer(
                run, scenario, ROOT / "training" / "data" / "private" / "demo-answer-key.jsonl"
            )
            output.append(run)
    except (urllib.error.URLError, OSError):
        parser.exit(
            2, "Could not prepare the local scenario or save its private evaluator record.\n"
        )
    print(json.dumps(output, indent=2))  # Resource IDs and observable probe status only.


if __name__ == "__main__":
    main()
