# Database and API contracts

FaultBrief's subscribing company is a **workspace**. The account experiencing a problem in that company's SaaS is an **affected customer**. These are different records.

For example, Acme SaaS subscribes to FaultBrief. BlueCo uses Acme's software and cannot export a report. Acme's support engineer creates an investigation inside Acme's workspace and selects BlueCo's customer record. A support engineer from Beta SaaS cannot read that investigation or attach BlueCo to Beta's workspace.

## Data model

All application tables and the Alembic version table live in the `faultbrief` PostgreSQL schema. Neon owns its `neon_auth` schema; application migrations do not manage it.

| Table              | Purpose and enforced relationships                                                                                          |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `users`            | Application identity keyed by verified JWT issuer and subject. No passwords or sessions.                                    |
| `workspaces`       | The subscribing company/team.                                                                                               |
| `memberships`      | User/workspace relationship, local role, and active flag. Unique per user/workspace.                                        |
| `customers`        | Affected SaaS accounts. External account IDs are unique within a workspace.                                                 |
| `integrations`     | Workspace-owned connector metadata. Credentials are represented by a private secret reference, excluded from API responses. |
| `investigations`   | Required workspace, affected customer, creating member, question, state, and execution timestamps.                          |
| `jobs`             | One queued job per investigation, with retry counts, availability, and a future lease.                                      |
| `tool_calls`       | Job/investigation/workspace scope and optional same-workspace integration. Calls are constrained to read-only metadata.     |
| `evidence`         | Investigation scope, source reference/version, redacted excerpt, observation time, and optional same-case tool call.        |
| `reports`          | One report per investigation, summary, supported root cause, confidence, limitations, and suggested team.                   |
| `report_citations` | Links a report to evidence in the **same investigation and workspace**.                                                     |
| `feedback`         | One response per report/user, matching report scope and workspace membership.                                               |

Records use UUID keys and timezone-aware timestamps. Composite foreign keys enforce customer/workspace and case/workspace pairs. Matching only an individual UUID is insufficient for these relationships. The API also verifies active workspace membership on every scoped request; these constraints are not a substitute for read authorization or Row Level Security.

Roles are `owner`, `admin`, `support`, and `viewer`. Owners/admins configure integration metadata; owners/admins/support create customers and investigations. Active viewers can read and submit report feedback. Membership role and revocation are read from the database, not a role asserted in a JWT or request body. Membership removal is currently represented by an inactive record, preserving authorship history.

## Investigation lifecycle

| State          | Meaning                                                          | Allowed next state                    |
| -------------- | ---------------------------------------------------------------- | ------------------------------------- |
| `queued`       | The case and its job have been persisted atomically.             | `running`, `failed`                   |
| `running`      | A future worker is executing the investigation.                  | `completed`, `inconclusive`, `failed` |
| `completed`    | Investigation finished with a supported result.                  | Terminal                              |
| `inconclusive` | Investigation finished without enough evidence for a root cause. | Terminal                              |
| `failed`       | Execution failed, including failure before starting.             | Terminal                              |

Running cases require a start time; terminal cases require a finish time. Completed/inconclusive cases require both, in chronological order. The service validates transitions and database constraints reject contradictory timestamps. The API does not accept caller-selected states or authors.

Job states describe execution (`queued`, `running`, `completed`, `failed`). An inconclusive investigation can have a completed job. Workers will claim jobs and update these records in the next milestone; creating a case currently leaves it queued.

## API surface

See [the exported OpenAPI contract](api/openapi.json), or start the backend and visit `http://127.0.0.1:8000/docs`.

| Method and route                                                          | Result                                                         |
| ------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `GET /health`                                                             | Public liveness; no database/provider availability claim.      |
| `GET /v1/me`                                                              | Provision/read the application identity from a verified token. |
| `POST /v1/workspaces`                                                     | Create a workspace and its owner membership atomically.        |
| `GET /v1/workspaces`                                                      | List only the caller's active workspaces.                      |
| `GET /v1/workspaces/{workspace_id}/memberships`                           | Read the workspace roster.                                     |
| `GET, POST /v1/workspaces/{workspace_id}/customers`                       | List/create affected accounts.                                 |
| `GET /v1/workspaces/{workspace_id}/customers/{customer_id}`               | Read a same-workspace account.                                 |
| `GET, POST /v1/workspaces/{workspace_id}/integrations`                    | List/create disabled connector metadata.                       |
| `GET, POST /v1/workspaces/{workspace_id}/investigations`                  | List/create scoped cases. Creation also queues a job.          |
| `GET /v1/workspaces/{workspace_id}/investigations/{investigation_id}`     | Read a scoped case.                                            |
| `GET .../investigations/{investigation_id}/jobs`                          | Read its execution records.                                    |
| `GET .../investigations/{investigation_id}/tool-calls`                    | Read its tool-call metadata.                                   |
| `GET .../investigations/{investigation_id}/evidence`                      | Read its redacted evidence.                                    |
| `GET .../investigations/{investigation_id}/report`                        | Read its report with scoped citations.                         |
| `POST .../investigations/{investigation_id}/reports/{report_id}/feedback` | Submit feedback as the authenticated member.                   |

List responses contain `items`, `limit`, and `offset`. Limit is 1–100; offset is 0–10,000. All request objects forbid extra fields. `401` means invalid/missing identity, `403` insufficient role, `404` unknown or inaccessible scope, `409` a resource/relationship conflict, `422` invalid input, and `503` unavailable/unconfigured dependencies. Database errors do not return SQL parameters or credentials.

`ReportDraft` is the strict internal output contract for a future model. Confidence must be a finite number between 0 and 1; a root-cause claim requires unique citations. The report persistence service checks that every cited evidence ID belongs to the case. Confidence is a declared score, not a calibrated probability; evaluation will determine how useful it is.

## Neon configuration and authentication

Read [the authentication flow and current implementation gaps](authentication.md). FaultBrief verifies Neon JWTs; signup/login uses the Neon SDK through the Next.js provider proxy; see the separate auth routes and setup walkthrough.

`Settings` reads the root `.env` and then `backend/.env`; the later file overrides matching variable names. Process environment values take priority. Use one database naming style when populating files: `DB_URL` or its canonical alias `DATABASE_URL`.

| Setting                                            | Meaning                                                                       |
| -------------------------------------------------- | ----------------------------------------------------------------------------- |
| `DB_URL` / `DATABASE_URL`                          | Backend-only PostgreSQL connection string.                                    |
| `AUTH_URL` / `NEON_AUTH_BASE_URL`                  | Managed Neon Auth base URL.                                                   |
| `JWKS_URL` / `NEON_AUTH_JWKS_URL`                  | Trusted HTTPS public-key endpoint.                                            |
| `MIGRATION_DATABASE_URL` / `DATABASE_URL_UNPOOLED` | Optional direct migration connection; otherwise the runtime URL is used.      |
| `AUTH_ISSUER`                                      | Optional issuer override; Managed Neon Auth defaults to the AUTH_URL origin.  |
| `AUTH_AUDIENCE`                                    | Optional audience enforcement when required by the provider's token contract. |

Send the short-lived Neon Auth **JWT**, not an opaque session cookie, as `Authorization: Bearer <token>`. The verifier uses the configured JWKS, constrains the token algorithm to its signing key, verifies signature/issuer/expiry/issue time/subject, and checks the audience when configured. It never follows a key URL supplied by the token. Signing keys are cached with refresh support. The current configured Neon key uses EdDSA; RS256/ES256 keys are also supported for compatible providers. See [Neon's managed-token verification guidance](https://neon.com/docs/compute/functions/authentication).

The Next.js browser signup/login flow is implemented; see [authentication](authentication.md). The backend does not collect or store Neon passwords. The public marketing samples remain prepared UI data, independent of these API routes. No worker, live diagnostics, or model execution is introduced by this milestone.

## Migrations and contract maintenance

```sh
pnpm run setup
pnpm run db:migrate
pnpm run db:check
pnpm run api:export
```

`db:migrate` applies the frozen Alembic revisions; startup never modifies the schema. `db:check` detects model/schema drift. `db:sql` emits the initial PostgreSQL DDL without including connection values. The initial migration creates only FaultBrief tables. Downgrades remove application tables, so rollback tests run only against a disposable database.

For a new schema change, generate and review a new revision:

```sh
node scripts/python.mjs run --project backend --locked alembic -c backend/alembic.ini revision --autogenerate -m "describe the schema change"
node scripts/python.mjs run --project backend --locked ruff format backend/migrations
```

Regenerate OpenAPI after route/schema changes. `pnpm run check` rejects a stale artifact. The artifact is generated with empty configuration and contains no Neon environment values.

## Testing

PostgreSQL tests upgrade, check drift, downgrade, re-upgrade, and verify unrelated schema preservation. Request tests use real EdDSA-signed test tokens and real PostgreSQL constraints, with synthetic identities and a stubbed JWKS network lookup. They do not exercise the browser's actual provider sign-in flow. The live Neon DB and JWKS connectivity are checked separately.

Tests read **only** `FAULTBRIEF_TEST_DATABASE_URL`; they never use the configured Neon connection string as a fallback. They refuse non-loopback hosts and require a disposable database name ending in `_test`. Without that variable, local database tests skip; CI requires it and provisions its own PostgreSQL service.

Use an existing disposable local Postgres database, or this optional Docker setup:

```sh
docker compose -p faultbrief-tests -f infra/compose.test.yml up -d
```

In PowerShell:

```powershell
$env:FAULTBRIEF_TEST_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5433/faultbrief_test'
pnpm run check
pnpm run smoke
```

The Docker service uses a pinned PostgreSQL 18 image, exposes only a loopback port, and contains disposable test data. Stop it with `docker compose -p faultbrief-tests -f infra/compose.test.yml down`. Native Postgres is also supported; Docker remains optional for development.
