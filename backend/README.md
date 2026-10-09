# Backend

FastAPI with a PostgreSQL data model, Alembic migrations, Neon JWT verification, and company/customer-scoped API contracts. The database stores investigations and queued jobs; worker execution and browser sign-in come in later milestones.

Run `pnpm run setup`, configure `backend/.env` using its example, apply `pnpm run db:migrate`, then use `pnpm run dev`. The existing `DB_URL`, `AUTH_URL`, and `JWKS_URL` names are supported. Actual environment files stay ignored.

Read [the database/API guide](../docs/database-api.md) for entity relationships, roles, state transitions, endpoint contracts, migrations, and disposable PostgreSQL testing. Inspect the API at `/docs` or use the versioned [OpenAPI artifact](../docs/api/openapi.json).

Dependencies remain locked in `uv.lock`. All model-training dependencies are separate from this lightweight API runtime. `/health` is liveness only; it does not poll Neon or imply a worker is running.
