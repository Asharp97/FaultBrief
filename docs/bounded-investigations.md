# Bounded model-selected investigation steps

This extends [reliable processing](reliable-processing.md). Apply migration `0004_bounded_model_calls` with `pnpm run db:migrate`, then restart the API and worker. `baseline` remains the default and uses the existing fixed diagnostic sequence. Enabling the new mode requires a model configured on the server; no new browser credentials are needed.

## Enable it

In ignored `backend/.env`, set `INVESTIGATION_MODE=model_selected`, plus the existing `MODEL_PROVIDER` (`openai` or `openai-compatible`), `MODEL_NAME`, `MODEL_ENDPOINT`, and `AI_PROVIDER_API_KEY`. The model must support strict function calling and structured report output. Configure `MODEL_INPUT_USD_PER_MILLION` and `MODEL_OUTPUT_USD_PER_MILLION` with the selected provider/model's current uncached input and completion prices. We deliberately do not guess prices for an unspecified model. Prices may be zero for a genuinely free local service or synthetic test fixture. A missing price prevents any model request (`budget_not_configured`). No paid inference is used by the automated tests.

Start with `pnpm run dev --worker`, connect a Ledger customer, and submit a ticket as in the [baseline walkthrough](baseline-investigation.md). The dashboard shows model-selected checks, request count, reserved cost estimate, stop reason, dispatch recommendation, and a model-request audit. A missing model configuration uses bounded baseline checks. If model configuration exists but pricing is missing, the run stops inconclusively without inference; configure prices or choose baseline mode.

## Selection and validation

At each step the server advertises only unused actions: read feature configuration, bounded jobs, bounded request logs, affected-user permissions, or the three approved runbooks. The model returns exactly one `choose_diagnostic_step` function call with an allowed action ID or `stop`. It can select the action; its arguments are constructed by the backend from the ticket's validated references and already collected scoped records. It cannot change the workspace/customer, URL, record limits, credentials, SQL, file path, or operation. Parallel tool calls, unknown actions, repeated actions, extra arguments, contradictory stops, refusals, and malformed responses are rejected before diagnostic execution. See [official OpenAI function-calling guidance](https://developers.openai.com/api/docs/guides/function-calling).

Requests use strict function schemas, `parallel_tool_calls=false`, a forced selection function, `store=false`, and 200 completion tokens. Every choice is checked locally even with provider-side schema enforcement. Ticket text and log/runbook content are treated as untrusted evidence. Prompt-injection resistance rests on the action boundary and scope enforcement, not a promise that a model always ignores malicious text. The model never sees lab answer keys or connector credentials.

The same evidence collector and rules verify the result regardless of tool order. It correlates exact job/request/member references before claiming a cause. The loop stops as soon as rules establish a supported completed finding, when the model reports missing information/no useful checks, when all actions are exhausted, or when a bound is reached. Invalid/unavailable model choices switch to the remaining bounded baseline checks; the report states that fallback occurred. Report explanation cannot change the supported cause, observed facts, citations, confidence ceiling, or dispatch team. Partial/ambiguous evidence produces an inconclusive finding rather than an invented cause.

## Limits and spending

| Setting                          | Default | Bound                                                                           |
| -------------------------------- | ------- | ------------------------------------------------------------------------------- |
| `INVESTIGATION_MAX_STEPS`        | 5       | 1–8 per attempt; each of the five available tools runs at most once             |
| `INVESTIGATION_MAX_SECONDS`      | 45      | 1–60 seconds for the model-selected collection and explanation per attempt      |
| `MODEL_MAX_CALLS`                | 6       | 1–10 requests across the whole investigation, including retries and explanation |
| `MODEL_BUDGET_USD`               | 0.02    | Positive, at most $1 reserved estimate across all attempts                      |
| `MODEL_MAX_INPUT_TOKEN_ESTIMATE` | 24,000  | 2,000–50,000 conservative input estimate per request                            |
| `MODEL_MAX_COMPLETION_TOKENS`    | 1,600   | Existing explanation limit; selection calls use 200                             |

Existing diagnostic timeout/record/response-size limits still apply. The complete model-selected deadline bounds both model phases; inference timeouts use only remaining time. Checkpoints and publication recheck the live job lease and requester membership. Timings exclude database transaction duration and process scheduling; this is bounded remote work, not a hard real-time deadline.

Before each model request, a transaction locks the job, rechecks access, increments its lifetime call count, and reserves a cost estimate in `model_calls`. Input estimation uses the UTF-8 payload byte count plus 1,024 protocol-overhead tokens; output estimation uses the configured completion cap. Charges are rounded up to six decimal places. This is a deliberately conservative estimate, **not provider-measured tokens or a guaranteed invoice cap**: current provider pricing, tokenization, extra fees, and billing controls still matter. Use provider-side account limits for an additional billing boundary.

Reservations are not refunded after timeout, invalid output, or process termination because the provider may have accepted/billed the request. A crash after reservation leaves a visible `reserved` entry; restarted workers inherit the same call count and reserved total. This avoids budget resets and repeated inference beyond the configured limits. Model-request audit states are reserved, succeeded, and failed. They contain scope, attempt, sequence, purpose, input estimate, completion cap, reservation amount, and safe error code; no raw prompts, provider replies, keys, or stack traces are stored in this audit. “Succeeded” describes a valid transport response; report content is separately validated and may fall back.

The scoped API `GET /v1/workspaces/{workspace_id}/investigations/{investigation_id}/model-calls` exposes the audit. Job reads add `investigation_mode`, `stop_reason`, `model_call_count`, and `reserved_model_cost_usd` (a decimal JSON string). Read-only diagnostic audit/evidence/report publication stays atomic, while request reservations and progress checkpoints persist earlier so they survive crashes.

## Dispatch and verification

Permission/configuration findings recommend **Account administration**; storage failures and timeout escalations recommend **Platform engineering**; unmatched/healthy cases recommend **Support engineering** for review. These are recommendations only. FaultBrief does not send messages, change permissions, retry exports, or perform remediation.

Run `pnpm run check` with a disposable loopback `FAULTBRIEF_TEST_DATABASE_URL`, then `pnpm run frontend:e2e`. Tests cover all Ledger scenarios, early supported stop, missing-information stop, partial step/runtime limits, refused/invalid/repeated/parallel selections, forbidden URL/customer arguments, budget rejection before inference, shared planner/explainer limits, retained reservations after worker termination, exact-reference correlation, and revocation between selection and tool execution. Browser cases use the real API/worker/PostgreSQL/Ledger with synthetic function calls and explanations. Bruno requests 18–20 review the audit, reconcile cost/count with job fields, and verify outsider denial. Real provider compatibility and answer quality still need evaluation with the model you select.

## Ground recommended procedures in documentation

A supported cause triggers one bounded local runbook retrieval when a diagnostic step remains; the search uses observed codes and the redacted ticket, preserving version/file/line citations. It does not consume another planner inference request. See [documentation retrieval](documentation-retrieval.md). To exercise the full pipeline without any model requests, use `pnpm run dev --worker --baseline` as described in [the first-investigation guide](testing-first-investigation.md).
