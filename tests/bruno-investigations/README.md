# Manual investigation workflow in Bruno

Follow [the baseline walkthrough](../../docs/baseline-investigation.md) first: apply migrations through 0004, configure the diagnostic key, approve a Ledger customer, and run `pnpm run dev --worker`. Open this collection in Bruno, select **Local**, and copy `.env.example` to ignored `.env`. Set your signed JWT, workspace ID, and the **FaultBrief affected-customer ID** printed by the operator connect command. These IDs differ from Ledger's source customer ID.

Run **01–05**, then repeat **06** until the investigation is **completed** or **inconclusive**. Continue **07–15** to review the report, validate citations against collected evidence, inspect read-only tool calls and the completed job, reject arbitrary context/unauthenticated access, and submit feedback. A failed case requires fixing configuration/access and submitting a new ticket; it has no report. Request 01 resets captured IDs, so do not rerun it mid-flow. Request 01 creates a fresh submission UUID; repeating 05 replays that case. Run 16–17 to verify replay and conflicting-payload rejection; feedback can be submitted once per user/report.

Optional request 14 uses a different account with no membership in this workspace. Fill `INVESTIGATION_OUTSIDER_TOKEN` and set `run_isolation=true`; otherwise it is skipped. No connector, operator, database, or model-provider credential belongs in this collection. JWTs expire, so refresh them through the auth collection/dashboard when needed.

For a first supported report use Ledger's feature-disabled scenario. Healthy cases describe the observed successful export, and timeout cases remain inconclusive. These tests accept a rules report without an inference key; `explanation_source` records whether a model explanation was used. The original application collection is a separate queued-state test mode and should run without the worker.

Run 18–20 to inspect model reservations, reconcile request count and estimated spending with the job, and verify a different account cannot read the audit. Baseline cases have zero model reservations; model-selected cases require [server-side model and pricing configuration](../../docs/bounded-investigations.md).

For a first customer after creating a workspace, follow [the guided model-free setup](../../docs/testing-first-investigation.md). Use the helper output’s FaultBrief `customer_id` (not `source_customer_id`) in this collection. Baseline mode needs no model tuning or inference key. Runbook evidence now preserves versioned Markdown file/line references.
