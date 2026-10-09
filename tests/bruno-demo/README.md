# Ledger manual tests in Bruno

Run pnpm run demo:configure, then pnpm run dev. Open this collection, select Local, and copy .env.example to ignored .env. Fill the app/operator/diagnostic keys from demo/.env. These keys belong to the test SaaS, not Neon Auth.

Send numbered requests top to bottom. IDs are captured automatically. Requests first verify health/auth, create a healthy customer, observe feature/permission/report/job/log records, download CSV, and enforce read-only/scope limits. The final groups create each fault, observe evidence, reset it, and verify a healthy job. Runs are real persisted synthetic records; rerunning creates new accounts.

This collection does not write the evaluator answer key. Use pnpm run demo:scenario -- seed-all when preparing graded cases. See [the full lab walkthrough](../../demo/README.md) for the UI, keys, reset behavior, and evaluator isolation.
