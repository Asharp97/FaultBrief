# FaultBrief manual API tests in Bruno

Open this directory as a **collection** in [Bruno](https://www.usebruno.com/), select **Local**, and run numbered folders in order. Each request has a purpose, prerequisites, expected status, and assertions in its Tests tab. Green means the expected behavior passed, including deliberate 401/403/404/409/422 responses.

## Prepare once

1. From the repository root, run `pnpm run setup` if needed, then `pnpm run db:migrate` against your development database. Keep Neon database/Auth settings in `backend/.env`.
2. Run `pnpm run dev`. Local assumes API port `8000` and demo port `8001`; edit `base_url` / `demo_url` in Local if you use other ports. If running only the API, set `run_demo_health=false`.
3. Obtain signed JWTs for **two different test users** from the Neon Auth provider configured for this backend. Put them in `tests/bruno/.env`, copied from `.env.example`. This file is ignored by Git. Use a third distinct test user only for the optional viewer tests.
4. Open the collection and select Local. Keep `run_report_fixture=false` and `run_viewer_tests=false` for the first pass. Use sequential execution; these requests share captured IDs.

`DB_URL`, `AUTH_URL`, and `JWKS_URL` configure the server; they are **not bearer tokens**. A Neon API key or opaque session token also will not work. For a signed-in Neon Auth client, its `authClient.token()` result contains the JWT at `data.token`; see [Neon authenticated client guidance](https://neon.com/docs/compute/functions/authentication). FaultBrief does not yet expose signup/login endpoints or a browser sign-in screen. You must sign in through your configured provider or a provider SDK test client to obtain these JWTs first.

Bruno reads the collection's local `.env` through [process environment variables](https://docs.usebruno.com/secrets-management/dotenv-file). No database credential belongs in that file. Refresh JWTs when they expire; do not paste them into tracked `.bru` files, screenshots, or reports. Restart/reopen Bruno after changing `.env` if it has cached the old values.

## What to test first

| Order | Folder                 | What you establish                                                         |
| ----- | ---------------------- | -------------------------------------------------------------------------- |
| 1     | 01 Readiness           | API health, OpenAPI, Swagger, ReDoc, optional demo health                  |
| 2     | 02 Identity            | Stable user A, distinct user B, missing/malformed token rejection          |
| 3     | 03 Company A setup     | Workspace → owner membership → customer → integration → case → queued job  |
| 4     | 04 Company B setup     | Independent company, same external customer ID, separate case              |
| 5     | 05 Validation          | Bad inputs, forged fields, duplicate rejection, pagination, write rollback |
| 6     | 06 Workspace isolation | Both companies stay separate across reads, writes, cases, and feedback     |
| 7     | 07 Report fixture      | Optional populated tool/evidence/report responses and feedback             |
| 8     | 08 Viewer permissions  | Optional viewer reads and feedback succeed; configuration/writes fail      |

Start by sending **01 Readiness / 01 API health and new run**. It resets captured core IDs and generates a unique `run_id`. Then send requests top to bottom, or use the collection runner. Do not run that reset request halfway through a session. IDs are runtime variables, so later requests work without editing URLs or request bodies. Missing prerequisites produce an explanatory script error.

A pass creates two synthetic workspaces, two customers, one disabled integration, and two queued investigations with their jobs. Each rerun starts a fresh pair of workspaces. These are real persisted development records; there is no delete endpoint or automatic cleanup. Keep this collection pointed at a development database. The workspace list is paginated and permits older records from previous runs.

**Current behavior:** no investigation worker is implemented. A freshly queued case has one queued job, empty tool/evidence lists, and no report (404). Those checks are deliberate. Integration creation saves disabled metadata; no external system is contacted. Health checks establish liveness only; `/v1/me` and setup exercise Auth/database connectivity.

## Optional: populated reports and viewer permissions

There is no report-creation or membership-management API yet. The operator-only `seed_fixture.py` creates a separate, clearly synthetic completed case and an optional viewer membership. It never runs diagnostics or calls a model. It requires the development database used by your API, rejects production settings, and only accepts a `Bruno manual A - ...` workspace, its own customer, and its active owner. It does not change existing roles or reactivate revoked memberships.

1. Finish folders 01–06. In Bruno's runtime variables, copy `workspace_a_id`, `customer_a_id`, and `user_a_id`.
2. For viewer tests, fill `FAULTBRIEF_BRUNO_TOKEN_VIEWER` with a third user's JWT, enable `run_viewer_tests`, and send **02 Identity / 06 Optional viewer identity** by itself. Copy the response's `id` (`user_viewer_id`). Do not run folder 08 yet.
3. From the repository root, substitute the captured UUIDs in this command:

   ```sh
   node scripts/python.mjs run --project backend --locked python tests/bruno/seed_fixture.py --workspace-id WORKSPACE_A_UUID --customer-id CUSTOMER_A_UUID --owner-user-id USER_A_UUID --confirm-synthetic-fixture
   ```

   For viewer tests, add `--viewer-user-id VIEWER_USER_UUID` to the same command.

4. Copy each `fixture_*` value printed by the helper into the Local environment. These are resource IDs, not credentials. Set `run_report_fixture=true`, then run folder 07 in order. If you supplied a viewer, leave `run_viewer_tests=true` and run folder 08 afterward.

The first feedback POST for each user expects 201; the next deliberately expects 409. To rerun these optional folders, run the helper again and replace the fixture IDs: it makes a new synthetic case/report without feedback. You can reuse the same manual workspace and viewer membership. The original queued investigation stays unchanged.

## Endpoint coverage

All **18 application operations** in `docs/api/openapi.json` have requests. Additional requests cover FastAPI documentation and the demo service's health endpoint. [coverage.json](coverage.json) maps every request to its method, contract path, expected status, and optional flag.

| Method | Path suffix under `/v1/workspaces/{workspace_id}`                 | Primary folder      |
| ------ | ----------------------------------------------------------------- | ------------------- |
| GET    | `/memberships`                                                    | 03 Company A setup  |
| POST   | `/customers`                                                      | 03 Company A setup  |
| GET    | `/customers`                                                      | 03 Company A setup  |
| GET    | `/customers/{customer_id}`                                        | 03 Company A setup  |
| POST   | `/integrations`                                                   | 03 Company A setup  |
| GET    | `/integrations`                                                   | 03 Company A setup  |
| POST   | `/investigations`                                                 | 03 Company A setup  |
| GET    | `/investigations`                                                 | 03 Company A setup  |
| GET    | `/investigations/{investigation_id}`                              | 03 Company A setup  |
| GET    | `/investigations/{investigation_id}/jobs`                         | 03 / 07             |
| GET    | `/investigations/{investigation_id}/tool-calls`                   | 03 / 07             |
| GET    | `/investigations/{investigation_id}/evidence`                     | 03 / 07             |
| GET    | `/investigations/{investigation_id}/report`                       | 03 (404) / 07 (200) |
| POST   | `/investigations/{investigation_id}/reports/{report_id}/feedback` | 03 (404) / 07 (201) |

The other four operations are `GET /health` (01), `GET /v1/me` (02), and `GET` / `POST /v1/workspaces` (03).

## Optional CLI execution

With the official Bruno CLI installed, from `tests/bruno`:

```sh
bru run --env Local --bail
```

The first run skips optional fixture/viewer requests. Once their IDs and flags are configured, run the optional folders only:

```sh
bru run "07 Report fixture" "08 Viewer permissions" --env Local --bail
```

Avoid parallel mode: later requests depend on previous responses. If exporting results, create the ignored `results/` directory first (`mkdir results`), write reports there, and omit authentication headers, for example `--reporter-json results/manual.json --reporter-skip-all-headers`. Response data remains in reports, so keep exports local.

## Reading failures

| Result                     | First thing to check                                               |
| -------------------------- | ------------------------------------------------------------------ |
| Missing-variable error     | Local selected, `.env` loaded, preceding setup requests completed  |
| 401 on an identity request | JWT expired, wrong issuer/provider, session token supplied instead |
| 503 on `/v1/me`            | Backend Auth/JWKS/DB configuration, network, migration status      |
| 404 on setup/read          | Correct captured workspace IDs and the matching test-user token    |
| 409 on first feedback      | That fixture already has feedback; create a fresh fixture          |
| Red test on a 4xx response | Compare expected status in Docs; many 4xx responses are deliberate |

This suite checks the API contract, scopes, and permissions. It does not claim coverage of future worker recovery, real model output, browser authentication, provider outages, load testing, or all possible JWT validation failures; existing automated auth tests cover signature/claim validation.
