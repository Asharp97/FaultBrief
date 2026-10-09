# Ledger: the deliberately breakable reporting SaaS

Ledger is the **customer's software**, separate from FaultBrief. Its web UI shows synthetic customers, member roles/permissions, feature settings, reports, CSV exports, jobs, and correlated request logs. A future FaultBrief investigator will read this service's diagnostic endpoints to explain a customer's problem.

## Try it

From the repository root:

```sh
pnpm run demo:configure
pnpm run dev
```

Open `http://127.0.0.1:8001`. Copy `DEMO_APP_TOKEN` from ignored `demo/.env` into **Reporting app token**, then connect. Expand **Lab operator**, supply `DEMO_OPERATOR_TOKEN`, and load the scenario controls. Create a scenario; its new customer is selected automatically. Press **Export report** to reproduce the issue, inspect **Export jobs** and **Request logs**, then **Reset this run to healthy** and download the CSV. Selecting Lee's viewer role also demonstrates a real server-side permission denial.

Scenario creation automatically probes the application's export logic, so evidence exists before the investigator reads it. App exports return 202 with a queued job; an in-process background task simulates completion/failure. This is a test simulator, not the FaultBrief investigation worker or a durable production queue. Diagnostic GET requests never advance jobs or mutate customer state.

## Repeatable scenarios

| Operator scenario    | Observable result                                                                       |
| -------------------- | --------------------------------------------------------------------------------------- |
| `healthy`            | Allowed permission/feature, completed export, downloadable CSV                          |
| `permission_removed` | Jamie lacks `exports.create`; request denied with 403 and a correlated log              |
| `feature_disabled`   | Customer export setting disabled; request denied with 409                               |
| `job_failed`         | Allowed request, failed job, observed artifact-write error                              |
| `ambiguous`          | Export timeout with partial downstream evidence; a definitive root cause is unsupported |

Global health remains green for every scenario: these failures affect a particular customer/request. Reset restores the selected run's permissions/settings, increments its generation/config version, removes its old synthetic jobs/logs, and creates a healthy probe. Other customer runs remain intact. Create a fresh scenario again to repeat a fault. Reset is deliberately destructive to that run's **synthetic** evidence, so evaluate it first.

## Keys and scopes

| Key                     | Allowed operations                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------- |
| `DEMO_DIAGNOSTIC_TOKEN` | Read customer context, members, reports, jobs, and bounded redacted logs            |
| `DEMO_APP_TOKEN`        | Reporting reads, create exports, download artifacts; member permissions still apply |
| `DEMO_OPERATOR_TOKEN`   | Application access plus scenario create/reset/catalog                               |

The tokens must be distinct and at least 32 characters. They are lab/integration keys, **not Neon user JWTs**. FaultBrief's real signup/login uses Neon; the separate demo simulates a reporting user by selecting a member under the lab application key. No passwords are stored here. Tokens in the UI are kept in memory, not browser storage. Lab controls are disabled when `DEMO_ENVIRONMENT=production`.

The demo persists its own SQLite database at `.tools/demo/reporting.sqlite3`, or `DEMO_DATABASE_PATH`. It never reads `DB_URL` or writes Neon. Schema version 1 is initialized for this isolated test service; future changes require a new explicit schema version. Core FaultBrief data remains managed by PostgreSQL/Alembic.

## Investigator API

`/docs` and [the frozen demo contract](../docs/api/demo-openapi.json) describe the reporting/diagnostic surface. Send the appropriate bearer key.

- `GET /health` is public liveness.
- `GET /v1/customers` lists synthetic affected accounts.
- `GET /v1/customers/{customer_id}` reads feature configuration/version.
- `GET .../members`, `GET .../reports` read member permissions and report data.
- `POST .../exports` creates a job with `member_id` and `report_id` (app/operator key).
- `GET .../jobs`, `GET .../jobs/{job_id}` read execution metadata.
- `GET .../jobs/{job_id}/download?member_id=...` downloads a completed CSV (app/operator key and member download permission).
- `GET .../logs?request_id=...` filters correlated logs; lists use bounded pagination.

Operator-only routes are `GET /lab/scenarios`, `POST /lab/runs` with `{ "scenario": "..." }`, and `POST /lab/runs/{run_id}/reset`. They are excluded from the public OpenAPI contract. The investigator's key cannot call them or create exports. Customer/resource pairs are checked in SQL, with composite foreign keys providing another scope check.

Use [the ordered Bruno demo collection](../tests/bruno-demo/README.md) for manual API checks.

## Private evaluation preparation

With the demo running, use the operator-only CLI:

```sh
pnpm run demo:scenario -- create permission_removed
pnpm run demo:scenario -- create ambiguous
pnpm run demo:scenario -- seed-all
pnpm run demo:scenario -- reset RUN_UUID
```

The CLI prints only resource IDs and observable probe status. It writes expected conclusions to ignored `training/data/private/demo-answer-key.jsonl`, keyed by random run UUID and generation. The HTTP service never imports or serves the evaluator module or this file. Model-facing APIs omit fault injection settings and expected answers. Customer names/IDs do not encode scenario names. Give the investigator only bounded HTTP tools using its diagnostic key: no operator key, arbitrary SQL, filesystem access, evaluator source, or answer-key ingestion.

UI controls create/reset interactive cases without writing an answer key. Use the CLI when preparing a graded dataset, and grade against the latest recorded generation; resetting through the UI invalidates the old generation. Keep evaluator records outside any RAG documentation vault.

## Verification

```sh
node scripts/python.mjs run --project backend --locked pytest tests/test_reporting_demo.py
pnpm run frontend:e2e
pnpm run demo:api
```

Automated tests create isolated temporary SQLite databases and synthetic keys. They verify all five scenarios and reset, actual export/download behavior, customer scope/FK checks, read-only access, answer-key separation, and browser reproduction/CSV download. They never use real Neon data.
