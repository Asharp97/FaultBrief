# Run a ticket investigation end to end

The baseline investigates Ledger export failures. It collects approved customer records with read-only tools, derives a finding with explicit rules, and optionally asks a configured model to explain that finding. It saves the tool audit, evidence, citations, report, and terminal state atomically. No export, permission change, account reset, or customer remediation is performed by the investigator.

## First working case

1. Apply the diagnostic-tools change before the baseline change. Run `pnpm run setup` and `pnpm run db:migrate` to install locked dependencies and apply migration `0002_investigation_reports` to your development database. This migration adds ticket references, observed facts, next steps, and report explanation source; existing records receive compatible defaults.
2. Run `pnpm run demo:configure`, then `node scripts/configure-diagnostics.mjs`. Start the services and worker with **`pnpm run dev --worker`**. The normal launcher without `--worker` still starts only the frontend, API, and Ledger.
3. Sign in at `http://localhost:3000/dashboard`, create a company workspace, and copy its workspace ID and your FaultBrief user ID.
4. Create a repeatable Ledger failure:

   ```sh
   pnpm run demo:scenario -- create feature_disabled
   ```

   The operator command prints `customer_id`, `member_id`, and the failing probe's `request_id`. It keeps the answer key private. You can also create the scenario in Ledger's operator dashboard.

5. Approve that source customer using the server-only command from [diagnostic tools](diagnostic-tools.md):

   ```sh
   node scripts/python.mjs run --project backend --locked python -m backend.app.diagnostics.cli connect --workspace-id WORKSPACE_UUID --owner-user-id OWNER_USER_UUID --source-customer-id LEDGER_CUSTOMER_UUID
   ```

6. In FaultBrief, choose **Investigate …** for your workspace. Select the newly connected affected customer and describe the failed revenue export. Open **Add request references** and enter Ledger's affected `member_id` and `request_id`. Submit **Investigate ticket**.
7. The case goes from queued to running to completed. Its report identifies disabled exports, cites the configuration/version and failed request, lists observed facts, and suggests an administrator review. You can inspect every cited record in **Collected evidence**.
8. Repeat with `permission_removed`, `job_failed`, `healthy`, or `ambiguous`, approving each new source customer. The timeout case is **inconclusive**: a timeout symptom and partial logs do not establish an underlying cause. Healthy evidence confirms the observed export completed rather than claiming all customer issues are fixed.

Each new scenario creates a distinct source customer. Resetting an existing Ledger run preserves that customer's identity; submit a new FaultBrief investigation after reset to observe the new records. Stored reports are point-in-time findings, not live views of future configuration changes.

## Optional model explanation

Rules reports work without an inference key or GPU. To enable the model, set these **server-only** values in ignored `.env` / `backend/.env`, then restart the worker:

```dotenv
MODEL_PROVIDER=openai
MODEL_NAME=replace-with-your-structured-output-model
AI_PROVIDER_API_KEY=replace-with-your-private-provider-key
MODEL_ENDPOINT=https://api.openai.com/v1/chat/completions
```

An OpenAI-compatible service can use `MODEL_PROVIDER=openai-compatible` and an explicitly configured endpoint. Production endpoints require HTTPS; local development can use loopback HTTP. The selected model must support the [strict JSON-schema response contract](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat). The adapter has one request per investigation, no automatic inference retry, bounded context/response size, and a token/time limit.

The model receives the redacted ticket, rules finding, and supporting evidence. It cannot change the rules-derived cause, observed facts, suggested team, or existing limitations, increase confidence, omit required evidence, cite an unknown record, or invent a quoted excerpt. Refused, incomplete, malformed, timed-out, or invalid explanations fall back to a usable rules report. The report shows whether its explanation came from rules, the model, or a fallback. Model prose and suggested next steps still require human review; structural/citation validation is not a general semantic-proof system. Confidence is a declared assessment, not a calibrated probability.

Defaults: 15-second inference timeout, 1,600 completion tokens, and 12,000 context characters. Override within validated bounds using `MODEL_TIMEOUT_SECONDS`, `MODEL_MAX_COMPLETION_TOKENS`, or `MODEL_MAX_CONTEXT_CHARS`. Connector credentials, database credentials, and lab/evaluator controls are excluded from model context.

## Worker operations and failure handling

`pnpm run worker:once` processes at most one eligible job. `pnpm run worker:run` polls continuously; idle polling defaults to five seconds. Continuous database polling can keep Neon compute active, so use `--once` for occasional local investigations when appropriate. `pnpm run dev --worker` connects the worker to the launcher's actual Ledger port; standalone commands require `DIAGNOSTIC_DEMO_URL` to match any custom port.

Workers claim jobs using PostgreSQL `FOR UPDATE SKIP LOCKED`. A 120-second lease and attempt counter fence stale workers; expired jobs can be reclaimed and exhausted jobs fail. Unexpected processing failures roll back partial evidence/reports and queue bounded retries. Expected missing diagnostics produce inconclusive reports. Requester membership is checked before collection and locked/rechecked before publication. Jobs revoked before collection fail; revocation during processing prevents publication of a new report. API reads remain workspace-scoped.

The minimal dashboard lists up to 100 affected customers and 50 recent investigations. It polls only the selected queued/running case, stops after two minutes, and offers refresh by selecting the case again. The legacy [Bruno application collection](../tests/bruno/README.md) should run without the worker for its queued-state checks; the new [investigation collection](../tests/bruno-investigations/README.md) exercises the worker flow.

## Verification

`pnpm run check` covers migrations, scoped diagnostics, rules, model failure/validation paths, transactional rollback, expired leases, exhausted jobs, and parallel claims. With a disposable loopback `FAULTBRIEF_TEST_DATABASE_URL`, `pnpm run frontend:e2e` exercises the real FastAPI/worker/PostgreSQL/Ledger pipeline through the dashboard, with synthetic auth and model responses. CI requires that database. Without it, the three investigation browser cases are skipped while existing auth/demo tests still run. Automated tests neither create real Neon users nor call a paid model.

## Submission replay and progress

Migration 0003 adds replay-safe submissions and durable worker progress. See [reliable processing](reliable-processing.md) for setup, API fields, restart recovery, and limits.
