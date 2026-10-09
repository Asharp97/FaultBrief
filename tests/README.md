# Tests

Current checks cover JWT signatures and claims, CORS and secret-safe errors, customer/workspace isolation, local role authority and revocation, queue persistence, scoped citations, read-only tool-call metadata, confidence bounds, and all investigation states.

PostgreSQL tests exercise the frozen migration's upgrade, drift check, downgrade, replay, and unrelated-schema preservation. They use only an explicit disposable loopback `FAULTBRIEF_TEST_DATABASE_URL` ending in `_test`, with per-test rollback. They never fall back to the configured Neon credentials.

See [database/API testing](../docs/database-api.md#testing) for native Postgres or the optional pinned Docker service. With that variable set, run `pnpm run check`. Without it, local database tests skip; CI requires and provides its own service. The startup smoke check uses real HTTP requests on unused ports.

Browser tests now cover Neon SDK signup/login against a loopback provider and reporting-lab reproduction, reset, and CSV download. Demo tests cover five scenarios, scoped exports/logs, read-only key enforcement, and evaluator separation. Next coverage should focus on the FaultBrief worker, bounded diagnostic orchestration, real provider sign-in, and the investigation dashboard.

## Manual API checks

Open [the ordered Bruno collection](bruno/README.md) to test every current endpoint, validation failures, workspace isolation, and optional synthetic report/viewer fixtures. Requests capture IDs and use an ignored local file for test JWTs.
