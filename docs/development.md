# Development guide

## Setup and start

1. Install Node.js 24, pnpm 11.24.0, and a working Python 3.12+ command with pip.
2. From the root, run `pnpm run setup`.
3. Run `pnpm run dev`.

Setup installs uv 0.12.23 into the repository's ignored `.tools/uv/` directory. uv provisions Python 3.12 in `.tools/python/` and synchronizes `backend/.venv/` from `backend/uv.lock`. Frontend dependencies use the existing pnpm lockfile. Environment files are created from examples only if missing.

The launcher binds local services to loopback addresses and stops only its own child process trees. It does not terminate other applications to free a port. The smoke check uses an isolated `.next-smoke/` cache and restores generated TypeScript configuration, so it can run alongside an existing frontend development server.

## Commands

| Command                                                                        | Purpose                                                             |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| `pnpm run setup`                                                               | Install the locked environments and create missing local env files  |
| `pnpm run dev`                                                                 | Start frontend, backend API, and demo service                       |
| `pnpm run smoke`                                                               | Verify startup on unused ports and stop the test processes          |
| `pnpm run check`                                                               | Format checks, Ruff, Python integration tests, frontend build/types |
| `pnpm run format`                                                              | Apply Prettier formatting to source and documentation               |
| `node scripts/python.mjs run --project backend ruff format backend demo tests` | Apply Python formatting                                             |
| `node scripts/python.mjs lock --project backend`                               | Resolve Python dependency changes into uv.lock                      |
| `pnpm --dir frontend add --save-exact PACKAGE`                                 | Add a frontend runtime dependency                                   |

`check` runs the production build before standalone type checking because Next.js generates route types during the build. Next.js may rewrite the generated `frontend/next-env.d.ts` when switching between development and production modes; treat it as generated framework state.

## Configuration

Root `.env` supplies defaults; `backend/.env` supplies Neon credentials and overrides matching keys. See [database/API configuration and testing](database-api.md). Blank optional credentials are ignored until their integration exists. `frontend/.env.local` contains public browser values only. Do not place a connection string or provider secret behind a `NEXT_PUBLIC_` prefix.

API CORS explicitly allows the configured frontend origin. This is a browser boundary, not authentication. The scoped API now verifies Neon JWTs and checks active database memberships. Browser sign-in is a separate next step.

## Dependency policy

- JavaScript: `frontend/pnpm-lock.yaml`, frozen installs, and the recorded pnpm version.
- Python: `backend/uv.lock`, locked installs, and Python 3.12.
- Heavy model training gets its own environment later.
- Update manifests and lockfiles together; do not edit generated lockfiles by hand.

## Delivery

Run checks and the startup smoke test before handing off tooling changes. Report the actual results and provide a commit message for every repository-changing handoff. Repository setup does not automatically make a commit or push.
