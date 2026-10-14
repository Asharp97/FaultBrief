# Customer-scoped diagnostic tools

These are independent Python operations, not model prompts. The only network method is GET; the tool client has no export creation, reset, lab catalog, arbitrary SQL, URL, or filesystem operation. Every source customer is approved in a server-private binding to one FaultBrief workspace/customer/integration. Users cannot grant themselves source access by guessing an external ID or putting a URL in a ticket.

## Prepare the read-only connector

1. Run `pnpm run demo:configure`, then `node scripts/configure-diagnostics.mjs`. The helper copies **only** Ledger's diagnostic key to ignored `backend/.env`; database and Auth configuration remain intact. Do not copy the app or operator key.
2. Run `pnpm run dev`. Create a FaultBrief workspace in the dashboard and copy its workspace ID and your FaultBrief user ID. In Ledger's operator dashboard or scenario CLI, create a scenario and note its `customer_id`. Scenario names/expected answers remain outside diagnostic requests.
3. From the repository root, approve that source customer:

   ```sh
   node scripts/python.mjs run --project backend --locked python -m backend.app.diagnostics.cli connect --workspace-id WORKSPACE_UUID --owner-user-id OWNER_USER_UUID --source-customer-id LEDGER_CUSTOMER_UUID
   ```

   This is a privileged local operator command using the configured database connection. It checks an active owner, reads the source's public customer record with the diagnostic key, creates/reuses the affected-customer record and enabled Ledger integration, and writes an atomic server-private allowlist under ignored `.tools/diagnostics/bindings.json`. It prints IDs only. A source customer cannot be assigned to two workspaces. It never reads the evaluator's answers.

## Read independently of any model

```sh
node scripts/python.mjs run --project backend --locked python -m backend.app.diagnostics.cli read --workspace-id WORKSPACE_UUID --customer-id FAULTBRIEF_CUSTOMER_UUID --tool features
```

Repeat with `--tool permissions`, `jobs`, `logs`, or `runbooks`. Permissions accepts optional `--member-id`; jobs accepts `--job-id` and `--limit`; logs accepts `--request-id` and `--limit`; runbooks accepts `--runbook-id export-permissions`, `export-feature`, or `export-jobs`. Invalid/irrelevant arguments fail validation. A failed read returns a stable error code and a nonzero exit status, without connection strings, credentials, or upstream error bodies.

Defaults: 20 records, 64 KiB response bytes, 3 seconds per request, 20 seconds total, and 6 network requests per toolset. Pagination is bounded; responses at the limit are marked as potentially truncated. Logs retain full/partial coverage and receive additional secret/email redaction. All returned customer IDs and supplied request correlations are checked. Runbooks are an explicit, versioned JSON catalog; they are operational guidance rather than a scenario answer key.

## Server-only configuration

`DIAGNOSTIC_DEMO_URL` defaults to `http://127.0.0.1:8001`; custom ports must match Ledger. Production requires HTTPS. `DIAGNOSTIC_DEMO_TOKEN`, `DIAGNOSTIC_BINDINGS_PATH`, and `DIAGNOSTIC_RUNBOOKS_PATH` remain server-only. Limits can be changed using `DIAGNOSTIC_MAX_RECORDS`, `DIAGNOSTIC_MAX_RESPONSE_BYTES`, `DIAGNOSTIC_REQUEST_TIMEOUT_SECONDS`, `DIAGNOSTIC_TOTAL_TIMEOUT_SECONDS`, and `DIAGNOSTIC_MAX_REQUESTS`, within their validated bounds. Never use a `NEXT_PUBLIC_` variable for a connector key.

HTTP errors, timeouts, malformed/oversized responses, unexpected fields, disabled integrations, missing bindings, and cross-customer responses fail closed. Tool tests use synthetic credentials and disposable data; no Neon account or inference key is needed. For deployment, provision the private binding file and read-only credential explicitly. This first connector supports one configured Ledger endpoint; different SaaS providers and per-company credential stores are later extensions.

## Markdown runbook search

The runbooks tool loads approved versioned Markdown via the catalog and supports `--query` and `--limit` (1–3). Results preserve file/version/line metadata and are ranked locally. See [documentation retrieval](documentation-retrieval.md). For local sample-account approval in one command, see [your first investigation](testing-first-investigation.md). The operator helper remains outside the investigator and does not submit a ticket.
