# FaultBrief

An evidence-led support investigation project: identify the affected customer, gather permitted records, and produce a reviewable finding and suggested handoff.

The repository contains the marketing preview, a Neon-backed API with verified JWT identity and workspace/customer scopes, versioned database migrations and OpenAPI contracts, and a demo-service foundation. Browser sign-in and the investigation worker are the next milestones.

## Repository layout

```text
frontend/       Next.js, Tailwind, GSAP, and the interactive product preview
backend/        Python API, settings, Python dependencies, and uv.lock
demo/           Separate demo service for future reproducible failure scenarios
training/       Model experiment conventions; heavy ML dependencies come later
tests/          Integration checks and future shared fixtures
docs/           Development guide and architecture notes
infra/          Infrastructure scope and future deployment configuration
scripts/        Cross-platform setup, development, and verification commands
```

## Prerequisites

- Node.js 24 (the reference version is recorded in `.node-version`).
- pnpm 11.24.0, matching `packageManager` in the root and frontend manifests.
- A working `python` command with pip, using Python 3.12 or newer. This bootstraps a local copy of uv; uv then provisions the backend's Python 3.12 environment.
- Internet access for the first dependency installation.

Docker is optional at this stage. No Neon account, model-provider key, or GPU is required to start the scaffold.

## One development workflow

From the repository root, run setup once:

```sh
pnpm run setup
```

Setup copies missing environment examples without overwriting existing files, installs the locked frontend dependencies, and installs the locked Python environment. uv and its caches are kept in the ignored `.tools/` directory.

Then start all three services with one command:

```sh
pnpm run dev
```

| Service            | Local address                |
| ------------------ | ---------------------------- |
| Marketing frontend | http://localhost:3000        |
| API health         | http://127.0.0.1:8000/health |
| API documentation  | http://127.0.0.1:8000/docs   |
| Demo health        | http://127.0.0.1:8001/health |

Press Ctrl+C to stop the processes started by the launcher. If a configured port is already occupied, choose other ports without stopping unrelated applications:

```sh
pnpm run dev --frontend-port 3100 --api-port 8100 --demo-port 8101
```

Changing frontend ports also requires adjusting the allowed origins in your local `.env` before adding frontend API calls.

## Verify changes

```sh
pnpm run check
pnpm run smoke
```

`check` verifies formatting, Python linting and integration tests, and the frontend production build and types. `smoke` starts the services on unused local ports, checks their HTTP responses, and stops its own processes.

```sh
pnpm run format
```

Use that command to apply the shared JavaScript/CSS/Markdown formatting rules. Python formatting is handled by Ruff; see [the development guide](docs/development.md).

For manual API testing, open [the ordered Bruno collection](tests/bruno/README.md). It covers all current application endpoints and includes setup, validation, workspace isolation, and optional synthetic report/viewer checks.

## Configuration and data

- Root `.env`: local defaults and optional server configuration.
- `backend/.env`: Neon database/Auth configuration, using `DB_URL`, `AUTH_URL`, and `JWKS_URL`.
- `frontend/.env.local`: public browser configuration only, such as the future API base URL.
- All environment files are ignored by Git; only the example files are versioned.
- `frontend/pnpm-lock.yaml` is the JavaScript dependency source of truth. `backend/uv.lock` is the Python source of truth.
- The API and demo health endpoints are liveness checks, not claims that a database, model, or integration is connected.

The homepage's samples use prepared synthetic data. The separate demo service currently exposes its health endpoint; reproducible customer failures are a later implementation step.

## Architecture and contribution

Read [database/API contracts](docs/database-api.md), [architecture](docs/architecture.md), [development](docs/development.md), [continuous integration](docs/continuous-integration.md), and [contribution conventions](CONTRIBUTING.md). Every repository-changing handoff includes a suggested commit message. The first milestone is one investigation verified against a deliberately introduced failure.

## License

FaultBrief source code is licensed under MIT. Dependencies and bundled font packages retain their own licenses.
