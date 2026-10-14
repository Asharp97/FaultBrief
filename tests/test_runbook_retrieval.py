import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.diagnostics.bindings import DiagnosticError
from backend.app.diagnostics.client import DiagnosticTools
from backend.app.diagnostics.config import DiagnosticSettings
from backend.app.diagnostics.contracts import RunbooksArgs, Scope
from backend.app.diagnostics.runbooks import search_runbooks

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "backend/runbooks/ledger.json"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("permission_denied exports.create", "export-permissions"),
        ("feature_disabled exports_enabled config_version", "export-feature"),
        ("STORAGE_WRITE_FAILED artifact storage", "export-jobs"),
        ("EXPORT_TIMEOUT downstream traces", "export-jobs"),
        ("export_completed completed job", "export-jobs"),
    ],
)
def test_keywords_rank_relevant_markdown_with_real_source_locations(query, expected):
    data, truncated = search_runbooks(CATALOG, RunbooksArgs(query=query, limit=1))
    item = data["items"][0]
    assert item["id"] == expected and item["version"] == "1"
    source = (CATALOG.parent / item["source_path"]).read_text(encoding="utf-8")
    lines = source.splitlines()
    assert item["content"] == source
    assert item["start_line"] == 1 and item["end_line"] == len(lines)
    assert source.startswith("# ") and item["source_path"].endswith(".v1.md")
    assert truncated is (data["matched_count"] > 1)


def test_case_insensitive_stable_ranking_and_no_match_do_not_invent_context():
    upper = search_runbooks(CATALOG, RunbooksArgs(query="STORAGE_WRITE_FAILED", limit=2))
    lower = search_runbooks(CATALOG, RunbooksArgs(query="storage_write_failed", limit=2))
    assert [item["id"] for item in upper[0]["items"]] == [item["id"] for item in lower[0]["items"]]
    data, truncated = search_runbooks(
        CATALOG, RunbooksArgs(query="unicorn cryptography blockchain")
    )
    assert data["items"] == [] and data["matched_count"] == 0 and not truncated
    books, _ = search_runbooks(CATALOG, RunbooksArgs())
    assert len(books["items"]) == 3


def test_explicit_id_keeps_search_within_the_requested_runbook():
    data, _ = search_runbooks(CATALOG, RunbooksArgs(runbook_id="export-feature", query="exports"))
    assert [item["id"] for item in data["items"]] == ["export-feature"]
    data, _ = search_runbooks(
        CATALOG, RunbooksArgs(runbook_id="export-feature", query="STORAGE_WRITE_FAILED")
    )
    assert data["items"] == []


@pytest.fixture
def catalog(tmp_path):
    shutil.copytree(CATALOG.parent, tmp_path / "runbooks")
    return tmp_path / "runbooks/ledger.json"


@pytest.mark.parametrize(
    "bad",
    [
        "traversal",
        "absolute",
        "wrong_version",
        "duplicate",
        "missing",
        "oversized",
        "blank",
        "malformed",
    ],
)
def test_invalid_catalogs_and_files_fail_closed_without_private_paths(catalog, bad):
    data = json.loads(catalog.read_text())
    entry = data["items"][0]
    file = catalog.parent / entry["path"]
    if bad == "traversal":
        entry["path"] = "../../training/data/private/answers.jsonl"
    if bad == "absolute":
        entry["path"] = "C:/private/passwords.txt"
    if bad == "wrong_version":
        entry["version"] = "2"
    if bad == "duplicate":
        data["items"][1] = entry
    if bad == "missing":
        file.unlink()
    if bad == "oversized":
        file.write_text("a" * 9000)
    if bad == "blank":
        file.write_text("  ")
    catalog.write_text("not-json" if bad == "malformed" else json.dumps(data))
    with pytest.raises(DiagnosticError, match="runbooks_unavailable") as error:
        search_runbooks(catalog, RunbooksArgs())
    assert "private" not in str(error.value) and "passwords" not in str(error.value)


def test_new_document_version_is_preserved_in_the_search_result(catalog):
    data = json.loads(catalog.read_text())
    entry = data["items"][0]
    previous = catalog.parent / entry["path"]
    entry["version"] = "2"
    entry["path"] = "ledger/export-permissions.v2.md"
    replacement = catalog.parent / entry["path"]
    replacement.write_text(previous.read_text() + "\nNew approved access-review procedure.\n")
    catalog.write_text(json.dumps(data))
    result, _ = search_runbooks(catalog, RunbooksArgs(runbook_id="export-permissions"))
    assert result["items"][0]["version"] == "2"
    assert result["items"][0]["source_path"].endswith(".v2.md")
    assert previous.exists() and "New approved" in result["items"][0]["content"]


def test_runbook_content_redacts_credentials_before_evidence(catalog):
    data = json.loads(catalog.read_text())
    entry = data["items"][0]
    file = catalog.parent / entry["path"]
    secret = "synthetic-diagnostic-" + "d" * 32
    file.write_text(
        file.read_text()
        + f"\npassword=private-value Bearer {secret} plain {secret} jimmy@example.invalid\n"
    )
    scope = Scope(
        workspace_id=uuid4(),
        customer_id=uuid4(),
        integration_id=uuid4(),
        source_customer_id=uuid4(),
    )
    settings = DiagnosticSettings(_env_file=None, demo_token=secret, runbooks_path=catalog)
    result = DiagnosticTools(scope, settings).run("runbooks", {"runbook_id": entry["id"]})
    assert result.state == "completed"
    assert all(
        value not in result.model_dump_json()
        for value in (secret, "private-value", "jimmy@example.invalid")
    )


@pytest.mark.parametrize(
    "args", [{"query": "x" * 513}, {"query": "   "}, {"limit": 4}, {"path": "private.txt"}]
)
def test_search_arguments_are_bounded(args):
    with pytest.raises(ValidationError):
        RunbooksArgs.model_validate(args)
