# Your first investigation, without model tuning

Yes: you can test the entire application before tuning a model. Start with the baseline rules, real Ledger diagnostic records, and versioned Markdown retrieval. No GPU, embedding service, inference key, or fine-tuned weights are required. Later, enable a pretrained model and compare it against the same labeled cases. Fine-tuning comes after that comparison if it improves a measured problem.

## Team versus affected customer

Your FaultBrief company workspace contains the people who investigate issues. Adding teammates does not create the accounts inside their product. An **affected customer** is an account in the app being investigated. For this local demo, that app is **Ledger**, our separate reporting SaaS. You do not need actual paying clients: a sample Ledger account has settings, members, export jobs, and logs that the investigator can read.

The message “No affected customers” means your workspace has no connected customer record yet. The investigator needs an approved mapping from a FaultBrief customer to a Ledger source customer. Merely guessing or pasting a Ledger UUID is not sufficient. The new local operator command creates a sample and approves that mapping for an active workspace owner. It keeps the lab key and evaluator answers away from the investigator.

## Start with the team you already created

Use a local development checkout and your existing workspace. From the repository root:

```sh
pnpm run demo:configure
node scripts/configure-diagnostics.mjs
pnpm run dev --worker --baseline
```

If the services are already running, stop that development launcher with Ctrl+C first and restart it with the flags above. Do not launch a second copy on the same ports. The baseline flag sets `INVESTIGATION_MODE=baseline` and `MODEL_EXPLANATION_ENABLED=false` for this worker process even if provider settings already exist in `.env`. Startup prints that no inference requests will be made. Existing configuration files are not rewritten to disable your model.

Open `/dashboard`, then choose **Investigate YOUR COMPANY**. In the empty customer panel, open **Try a local Ledger sample** and click **Copy demo setup command**. It includes the selected workspace UUID and your signed-in FaultBrief user UUID. Run it in a second terminal at the repository root, for example:

```sh
pnpm run demo:connect -- --workspace-id WORKSPACE_UUID --owner-user-id USER_UUID
```

The default scenario is `feature_disabled`. The command checks active workspace ownership before creating any sample, uses the private local operator key to prepare Ledger, writes the evaluator's expected answer under ignored `training/data/private/`, and uses the read-only diagnostic key to connect that customer. It prints only resource IDs, a neutral ticket question, and optional request references. It never runs the investigator, calls a model, sends an external message, or changes real customer permissions. Existing demo/diagnostic keys are reused; a conflicting configured diagnostic key is rejected instead of overwritten.

Wait for `"status": "connected"`, then:

1. Click **Refresh customers** in FaultBrief.
2. Select the new Ledger sample in **Affected customer**.
3. Enter: **Why did this customer's revenue export fail?**
4. Optionally expand **Add request references** and paste `context.member_id`, `context.request_id`, and `context.job_id` (when present) from the command's output. They match that sample's failing attempt. For one fresh sample they are not required.
5. Click **Investigate ticket**. The case should move from queued to running to completed.
6. Review the finding: exports are disabled for this customer. Inspect the configuration version, rejected request, cited Markdown runbook/file/line range, uncertainty, and suggested administrator review. A model-free report says **Evidence-based baseline** and has no model requests.

The **FaultBrief `customer_id`** is what the form/API uses; `source_customer_id` belongs to Ledger. They are different UUIDs. The dashboard handles that difference after connection, so you do not have to paste a customer UUID manually. The copied command is shown only in development to workspace owners; the CLI itself rechecks ownership and only permits loopback Ledger setup outside production. No public API endpoint can invoke lab preparation.

## Try the other cases

Add `--scenario SCENARIO` to the setup command; each invocation creates another isolated sample account and connection. Refresh customers and submit a neutral ticket for that account:

| Scenario             | Expected baseline behavior                                                                                       |
| -------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `feature_disabled`   | Completed finding: exports are disabled; account administration reviews settings.                                |
| `permission_removed` | Completed finding: the affected user lacks `exports.create`; account administration reviews access.              |
| `job_failed`         | Completed finding: artifact storage rejected the write; platform engineering investigates the underlying reason. |
| `healthy`            | Completed observation: this export succeeded; do not claim every issue is fixed.                                 |
| `ambiguous`          | Inconclusive finding: a timeout/partial logs do not establish the root cause.                                    |

For a custom Ledger port, append `--base-url http://127.0.0.1:PORT` to `demo:connect`. Use the port printed by the launcher. `pnpm run demo:connect -- --help` shows arguments without creating configuration or records.

## If the case does not finish

- **No customers:** run the copied connection command successfully, then refresh. Creating a team or a generic customer metadata record does not itself approve a diagnostic connection.
- **Setup rejected:** check the workspace/user IDs, active owner role, running Ledger service, and matching diagnostic key. Start with the setup commands above. The CLI shows a safe error code without printing credentials.
- **Queued indefinitely:** the worker is not running; restart with `--worker --baseline`, or use a configured standalone worker. The frontend and API alone do not process jobs.
- **Inconclusive:** inspect missing records, mismatched references, or failed diagnostic checks. The timeout case is deliberately inconclusive.
- **Already running on that port:** stop your old launcher before starting another one. Do not stop unrelated services.

This change does not add a database migration or require pgvector. Your existing schema migrations must already be applied; use `pnpm run db:migrate` if your checkout's schema is behind. For periodic testing, you can stop the worker after reviewing the report instead of keeping database polling active.

## What to test before fine-tuning

First verify signup, workspace access, customer connection, ticket submission, worker recovery, evidence scope/citations, Markdown relevance/source versions, and the expected healthy/ambiguous behavior. The API/browser/manual tests cover these system behaviors. Use the private answer key only in evaluation; it must never become model context.

After the baseline works, choose a pretrained model that supports the bounded tool/report interfaces and measure cause correctness, citation support, appropriate inconclusive responses, dispatch accuracy, runtime, and inference usage against those same cases. You can use a pretrained model without tuning it. Decide whether training helps only after you have that comparison. Synthetic automated responses verify contracts/failure paths; they do not measure a real model's answer quality.

With disposable loopback PostgreSQL configured in `FAULTBRIEF_TEST_DATABASE_URL`, run:

```sh
pnpm run check
pnpm run frontend:e2e
```

The automated suites use real API/worker/database/Ledger behavior and synthetic auth/model responses. The baseline tests make no inference requests even with a configured synthetic provider key. They do not create live Neon users or modify your live workspace. The existing [Bruno investigation collection](../tests/bruno-investigations/README.md) can also be used with the newly connected FaultBrief customer and a JWT copied from your dashboard.
