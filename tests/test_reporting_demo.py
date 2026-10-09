import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from demo.app.config import DemoSettings
from demo.app.main import create_app
from demo.evaluation.control import record_answer

KEYS = {
    "operator": "operator-" + "o" * 32,
    "app": "app-" + "a" * 32,
    "diagnostic": "diagnostic-" + "d" * 32,
}


def headers(role):
    return {"Authorization": "Bearer " + KEYS[role]}


@pytest.fixture
def lab(tmp_path):
    app = create_app(
        DemoSettings(
            _env_file=None,
            environment="test",
            database_path=tmp_path / "demo.sqlite3",
            **{role + "_token": key for role, key in KEYS.items()},
        )
    )
    with TestClient(app) as client:
        yield client, app.state.store


def create(client, scenario):
    response = client.post("/lab/runs", headers=headers("operator"), json={"scenario": scenario})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "scenario,status,state,error",
    [
        ("healthy", 202, "completed", None),
        ("permission_removed", 403, None, None),
        ("feature_disabled", 409, None, None),
        ("job_failed", 202, "failed", "STORAGE_WRITE_FAILED"),
        ("ambiguous", 202, "failed", "EXPORT_TIMEOUT"),
    ],
)
def test_each_scenario_is_created_observed_and_reset(lab, scenario, status, state, error):
    client, _store = lab
    run = create(client, scenario)
    base = f"/v1/customers/{run['customer_id']}"
    assert run["probe"]["status_code"] == status
    assert client.get("/health").json()["status"] == "ok"
    jobs = client.get(base + "/jobs", headers=headers("diagnostic")).json()["items"]
    if state is None:
        assert jobs == []
    else:
        assert len(jobs) == 1 and jobs[0]["state"] == state and jobs[0]["error_code"] == error
        assert jobs[0]["created_at"] <= jobs[0]["started_at"] <= jobs[0]["finished_at"]
    logs = client.get(base + "/logs", headers=headers("diagnostic")).json()
    assert logs["coverage"] == ("partial" if scenario == "ambiguous" else "full")
    assert any(row["request_id"] == run["probe"]["request_id"] for row in logs["items"])
    reset = client.post(f"/lab/runs/{run['run_id']}/reset", headers=headers("operator"), json={})
    assert reset.status_code == 200 and reset.json()["generation"] == 2
    new_jobs = client.get(base + "/jobs", headers=headers("diagnostic")).json()["items"]
    assert len(new_jobs) == 1 and new_jobs[0]["state"] == "completed"
    config = client.get(base, headers=headers("diagnostic")).json()
    assert config["exports_enabled"] and config["config_version"] == (
        3 if scenario == "feature_disabled" else 2
    )
    new_logs = client.get(base + "/logs", headers=headers("diagnostic")).json()
    assert new_logs["coverage"] == "full"
    assert all(row["request_id"] != run["probe"]["request_id"] for row in new_logs["items"])


def test_actual_export_creation_download_and_member_permission_enforcement(lab):
    client, _store = lab
    run = create(client, "healthy")
    base = f"/v1/customers/{run['customer_id']}"
    response = client.post(
        base + "/exports",
        headers=headers("app"),
        json={"member_id": run["member_id"], "report_id": run["report_id"]},
    )
    assert response.status_code == 202 and response.json()["state"] == "queued"
    job_id = response.json()["id"]
    assert (
        client.get(base + f"/jobs/{job_id}", headers=headers("diagnostic")).json()["state"]
        == "completed"
    )
    csv = client.get(
        base + f"/jobs/{job_id}/download?member_id={run['member_id']}", headers=headers("app")
    )
    assert csv.status_code == 200 and "2026-09,18000" in csv.text
    members = client.get(base + "/members", headers=headers("app")).json()["items"]
    viewer = next(m for m in members if m["role"] == "viewer")
    assert (
        client.get(
            base + f"/jobs/{job_id}/download?member_id={viewer['id']}", headers=headers("app")
        ).status_code
        == 403
    )
    assert (
        client.post(
            base + "/exports",
            headers=headers("app"),
            json={"member_id": viewer["id"], "report_id": run["report_id"]},
        ).status_code
        == 403
    )


def test_read_only_key_cannot_mutate_or_see_operator_controls_or_answers(lab, tmp_path):
    client, _store = lab
    run = create(client, "job_failed")
    base = f"/v1/customers/{run['customer_id']}"
    before = client.get(base + "/logs", headers=headers("diagnostic")).json()
    assert client.get("/lab/scenarios", headers=headers("diagnostic")).status_code == 403
    assert (
        client.post(
            "/lab/runs", headers=headers("diagnostic"), json={"scenario": "healthy"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/lab/runs/{run['run_id']}/reset", headers=headers("diagnostic"), json={}
        ).status_code
        == 403
    )
    assert (
        client.post(
            base + "/exports",
            headers=headers("diagnostic"),
            json={"member_id": run["member_id"], "report_id": run["report_id"]},
        ).status_code
        == 403
    )
    for suffix in ["", "/members", "/reports", "/jobs", "/logs"]:
        response = client.get(base + suffix, headers=headers("diagnostic"))
        assert response.status_code == 200
        assert not any(
            key in response.text
            for key in [
                "fault_mode",
                "expected_root_cause",
                "expected_investigation_state",
                "scenario",
            ]
        )
    assert client.get(base + "/logs", headers=headers("diagnostic")).json() == before
    public_contract = client.get("/openapi.json").text
    assert "/lab/" not in public_contract and "permission_removed" not in public_contract
    private = tmp_path / "private" / "answers.jsonl"
    record_answer(run, "job_failed", private)
    assert json.loads(private.read_text())["expected_root_cause"] == "artifact_write_failure"
    for route in [
        "/evaluation/answers",
        "/answer-key",
        "/assets/../evaluation/control.py",
        "/assets/../.env",
    ]:
        assert client.get(route, headers=headers("diagnostic")).status_code == 404


def test_customer_scope_is_enforced_in_api_and_database(lab):
    client, store = lab
    a, b = create(client, "healthy"), create(client, "healthy")
    base = f"/v1/customers/{a['customer_id']}"
    assert (
        client.get(
            base + f"/jobs/{b['probe']['job_id']}", headers=headers("diagnostic")
        ).status_code
        == 404
    )
    assert (
        client.post(
            base + "/exports",
            headers=headers("app"),
            json={"member_id": b["member_id"], "report_id": a["report_id"]},
        ).status_code
        == 404
    )
    assert (
        client.post(
            base + "/exports",
            headers=headers("app"),
            json={"member_id": a["member_id"], "report_id": b["report_id"]},
        ).status_code
        == 404
    )
    with pytest.raises(sqlite3.IntegrityError), store.connection() as db:
        db.execute(
            "UPDATE export_jobs SET customer_id=? WHERE id=?",
            (a["customer_id"], b["probe"]["job_id"]),
        )
    client.post(f"/lab/runs/{a['run_id']}/reset", headers=headers("operator"), json={})
    assert (
        len(
            client.get(
                f"/v1/customers/{b['customer_id']}/jobs", headers=headers("diagnostic")
            ).json()["items"]
        )
        == 1
    )


def test_invalid_auth_input_and_pagination_fail_safely(lab):
    client, _store = lab
    assert client.get("/v1/customers").status_code == 401
    assert (
        client.get("/v1/customers", headers={"Authorization": "Bearer invalid"}).status_code == 401
    )
    assert client.get("/v1/customers?limit=101", headers=headers("diagnostic")).status_code == 422
    assert client.get("/v1/customers/not-a-uuid", headers=headers("diagnostic")).status_code == 422
    assert client.get(f"/v1/customers/{uuid4()}", headers=headers("diagnostic")).status_code == 404
    assert (
        client.post("/lab/runs", headers=headers("app"), json={"scenario": "healthy"}).status_code
        == 403
    )


def test_lab_controls_are_disabled_in_production(tmp_path):
    app = create_app(
        DemoSettings(
            _env_file=None,
            environment="production",
            database_path=tmp_path / "prod.sqlite3",
            **{role + "_token": key for role, key in KEYS.items()},
        )
    )
    with TestClient(app) as client:
        assert (
            client.post(
                "/lab/runs", headers=headers("operator"), json={"scenario": "healthy"}
            ).status_code
            == 403
        )
