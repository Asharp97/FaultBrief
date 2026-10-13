# Reliable investigation processing

Run `pnpm run db:migrate` to apply migration `0003_reliable_jobs`, then restart the API and worker. Existing cases keep their identity; old jobs receive compatible phase defaults. Development tests use a disposable local database, never the configured Neon database.

## Submission retries

Include a client-generated UUID `submission_id` in `POST /v1/workspaces/{workspace_id}/investigations`. Keep the same UUID and payload when retrying after a timeout or lost response. A PostgreSQL unique constraint on workspace/creating member/submission ID and `INSERT ... ON CONFLICT` serialize concurrent replays. Case creation and its single job share a transaction. Replays return HTTP 201 and the original case, including its current state. Reusing the ID with a different normalized customer/question/context returns HTTP 409. Another member or workspace has a separate key namespace, and every replay still requires current writer access and a same-workspace customer.

The dashboard retains the UUID when the open form's submission fails, and replaces it when the payload changes or submission succeeds. This handles lost-response retries in the same open form. API integrations must persist their own key across process/page restarts. Requests without `submission_id` remain compatible and create a new case; identical text alone is not a reliable ticket identity. A genuinely new investigation, including a later retry after correcting the customer's configuration, uses a new UUID.

## Progress and recovery

`GET .../investigations/{id}/jobs` includes `phase`, `completed_steps`, `attempts`, `max_attempts`, `heartbeat_at`, `lease_until`, `available_at`, and `last_error_code`. The dashboard displays the phase and completed diagnostic checks while polling. These are durable checkpoints, not an estimated percentage. Job phases are queued, claimed, collecting, explaining, publishing, retry_wait, completed, and failed. An inconclusive report still has a completed job.

Workers claim with `FOR UPDATE SKIP LOCKED`, commit a fixed 120-second lease, and recheck the attempt and exact lease before every boundary and publication. The lease must still be in the future, even if no replacement worker has claimed it yet. Checkpoints update the heartbeat without renewing the lease. Diagnostic/model calls are bounded to finish within it. Requester membership is checked at each checkpoint and locked before final publication. No database transaction stays open across diagnostic or inference requests.

A worker process termination leaves the job and last checkpoint in PostgreSQL. After lease expiry, a new worker reclaims it, resets per-attempt progress, records `lease_expired`, and repeats the bounded reads. Final evidence/tool audits/report and terminal state publish atomically. A stale worker cannot publish or execute subsequent checks after losing its claim. An already-started remote request cannot be cancelled by a later membership revocation. Reads and model requests may repeat after crashes; this is at-least-once execution with one durable report, not exactly-once inference billing.

Unexpected processing failures roll back partial output, record only `processing_error` or `database_error`, and schedule 5/10-second retries for the default three attempts (the delay formula is exponential and capped at 60 seconds). Attempts exhausted after a crash or retry become visibly failed. Missing diagnostics produce an inconclusive report. Private exception messages, credentials, SQL, and provider responses are never persisted as job failure descriptions. `last_error_code` preserves the most recent recovery/failure reason even if a later attempt succeeds.

## Verify locally

Use a disposable loopback database whose name ends in `_test`; set `FAULTBRIEF_TEST_DATABASE_URL`, then run `pnpm run check` and `pnpm run frontend:e2e`. Tests simulate termination after a committed check, restart/reclaim, concurrent duplicate submissions, expired/stale leases, exhausted retries, revocation mid-collection, and a browser losing its response after the case was saved. They use real PostgreSQL transactions and synthetic model/auth responses; no paid model call is required. Bruno investigation requests 16 and 17 exercise a successful replay and conflicting payload.
