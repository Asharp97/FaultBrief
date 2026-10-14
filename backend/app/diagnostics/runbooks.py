import re
from collections import Counter
from pathlib import Path

from pydantic import Field, ValidationError, model_validator

from .bindings import DiagnosticError
from .contracts import Contract, Runbook, RunbooksArgs

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "did",
    "do",
    "for",
    "from",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "we",
    "what",
    "when",
    "why",
    "with",
}


class Entry(Contract):
    id: str = Field(pattern=r"^export-(permissions|feature|jobs)$")
    version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,2}$", max_length=40)
    title: str = Field(min_length=1, max_length=200)
    path: str

    @model_validator(mode="after")
    def approved_file(self):
        if self.path != f"ledger/{self.id}.v{self.version}.md":
            raise ValueError("Use a versioned Markdown file belonging to this runbook.")
        return self


class Catalog(Contract):
    items: list[Entry] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def unique_active_versions(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Choose one active version for each runbook.")
        return self


def terms(value):
    tokens = re.findall(r"[a-z0-9]+(?:[._][a-z0-9]+)*", value.casefold())
    # Keep exact error/permission codes and also match their individual words.
    expanded = [
        part
        for token in tokens
        if "." in token or "_" in token
        for part in re.split(r"[._]", token)
    ]
    return [term for term in [*tokens, *expanded] if term not in STOP_WORDS]


def search_runbooks(path: Path, arguments: RunbooksArgs):
    try:
        if path.is_symlink() or path.stat().st_size > 32768:
            raise ValueError("Catalog unavailable")
        catalog = Catalog.model_validate_json(path.read_text(encoding="utf-8"))
        root = path.parent.resolve()
        books = []
        for entry in catalog.items:
            candidate = root / entry.path
            if (
                candidate.is_symlink()
                or not candidate.resolve().is_relative_to(root)
                or candidate.stat().st_size > 8192
            ):
                raise ValueError("Runbook unavailable")
            content = candidate.read_text(encoding="utf-8")
            if not content.strip():
                raise ValueError("Empty runbook")
            books.append(
                Runbook(
                    id=entry.id,
                    version=entry.version,
                    title=entry.title,
                    content=content,
                    source_path=entry.path,
                    start_line=1,
                    end_line=len(content.splitlines()),
                )
            )
    except (OSError, ValueError, ValidationError):
        raise DiagnosticError("runbooks_unavailable") from None
    if arguments.runbook_id:
        books = [book for book in books if book.id == arguments.runbook_id]
        if not books:
            raise DiagnosticError("runbook_not_found")
    query = set(terms(arguments.query or ""))
    ranked = []
    for book in books:
        title, body = Counter(terms(book.title + " " + book.id)), Counter(terms(book.content))
        score = sum(4 * min(title[term], 2) + min(body[term], 3) for term in query)
        if not arguments.query or score > 0:
            ranked.append((score, book))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].id))
    selected = [book.model_dump(mode="json") for _, book in ranked[: arguments.limit]]
    return {"items": selected, "query": arguments.query, "matched_count": len(ranked)}, len(
        ranked
    ) > arguments.limit
