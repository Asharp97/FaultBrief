# Contributing to FaultBrief

## Change reporting

Every repository-changing response or handoff must include:

1. A concise explanation of what changed.
2. The verification actually performed, including any limitation.
3. A suggested commit message describing the final changes.

Prefer short imperative Conventional Commit messages, for example:

```text
chore: establish repository structure and development tooling
```

Providing a message does not mean creating a commit. Commits and pushes require an explicit user request. Preserve unrelated working-tree changes.

## Development conventions

- Use pnpm for frontend dependencies and commit `frontend/pnpm-lock.yaml` when they change.
- Use uv for Python dependencies and commit `backend/uv.lock` when they change.
- Run `pnpm run check`; use `pnpm run smoke` after startup or configuration changes.
- Keep frontend formatting in Prettier and Python formatting/linting in Ruff.
- Never commit actual environment files, credentials, private data, tool caches, or model checkpoints.
- Add meaningful tests for permissions, data boundaries, job lifecycle, and investigation outcomes as those features arrive.
- Keep tests deterministic unless they explicitly evaluate a live model. No live-model calls belong in basic formatting or unit checks.
