# Versioned documentation retrieval

The Ledger diagnostic tool now loads a small approved catalog of **Markdown runbooks** and performs local keyword search. Structured permissions, feature settings, jobs and logs keep using their existing scoped ordinary reads. No embeddings, vector database, paid reranker, or model call is needed to retrieve these documents.

## Corpus and versions

`backend/runbooks/ledger.json` is the trusted manifest. It selects one active version for each of the three approved runbook IDs and records its title, version, and relative Markdown filename. The initial files are `ledger/export-permissions.v1.md`, `ledger/export-feature.v1.md`, and `ledger/export-jobs.v1.md` under `backend/runbooks/`.

Publish changes as a new file/version, update that entry in the manifest, and retain old version files for audit. The reader requires each path to match `ledger/ID.vVERSION.md`; arbitrary paths, duplicate active IDs, symlinks/escapes outside the catalog directory, malformed JSON, blank/oversized Markdown and unapproved IDs fail closed. The manifest is limited to 32 KiB/three active entries, each source to 8 KiB and 4,000 characters. It reads trusted local files only; it does not fetch a URL found in a ticket or document.

## Search

`runbooks` accepts optional `query` (1–512 characters), `limit` (1–3), and an approved `runbook_id`. Without a query it returns the catalog; with a query it ranks matching files by case-insensitive keyword overlap, weighting titles/IDs above body occurrences. Exact permission/error codes and their component words are searchable; common English stop words are ignored. Ties use stable runbook IDs. No matches return an empty successful result, not fabricated context.

The collector constructs the query from the redacted ticket plus observed events/error codes, and requests the two highest-ranked matching documents. The model cannot supply a filename, URL, customer override or unbounded result limit. Baseline investigations read documentation after diagnostic records. Model-selected investigations also retrieve a useful runbook after a supported cause when a diagnostic step remains; this local lookup requires no extra inference request and respects the step/runtime bounds. Missing documentation is recorded as a limitation instead of changing an observed cause into a guess.

To read/search independently of any model, after a customer is approved:

```sh
node scripts/python.mjs run --project backend --locked python -m backend.app.diagnostics.cli read --workspace-id WORKSPACE_UUID --customer-id FAULTBRIEF_CUSTOMER_UUID --tool runbooks --query "feature_disabled exports_enabled" --limit 1
```

## Evidence and citations

Each result includes the active version, relative source file, exact start/end lines, and full bounded Markdown text. The current documents are small, so the retrieved unit is one file. Evidence stores the redacted text snapshot and a reference such as `runbook:ledger/export-feature.v1.md#L1-L13`, with `source_version="1"`. Lines reflect the actual source at retrieval time. Citation validation still requires an evidence record in the same investigation/workspace and exact quoted text from the stored redacted excerpt. Changing the active manifest version does not change a saved report's evidence.

Runbook text is treated as evidence, never executable instructions. Secrets/emails and the configured diagnostic key are redacted before evidence/model context. Approved Ledger runbooks are shared platform procedures, not uploaded per-company private vault documents. The private evaluator answer key is outside this catalog and inaccessible through the diagnostic tool. Uploaded customer documentation and its tenant access controls are a separate future capability.

## When to add vectors

Keyword retrieval is sufficient for this three-file corpus and the observed Ledger error codes. Add embeddings/pgvector only after representative tests show keyword retrieval misses relevant documentation (for example, paraphrased questions across a larger corpus). Keep ordinary structured queries for logs/permissions and preserve the same scope/version/source/citation guarantees. This milestone intentionally adds no vector infrastructure or embedding dependency.

Tests verify ranking for permission/config/storage/timeout/completion cases, case-insensitive stable results, no-match and bounded search behavior, source text/line ranges, a new active version, privacy redaction, invalid/missing/oversized sources, and retrieval/citations in a real model-free investigation. [Your first investigation](testing-first-investigation.md) explains how to exercise the app manually without tuning a model.
