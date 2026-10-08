# Backend

Python/FastAPI foundation with validated environment settings, a liveness endpoint, and an explicit local CORS policy. It does not yet connect to Neon, run a model, or expose customer diagnostic operations.

Use the root `pnpm run setup` and `pnpm run dev` commands. Dependencies are declared in `pyproject.toml` and resolved in `uv.lock`. Python 3.12 is the isolated backend runtime; heavy model-training dependencies are deferred.

`app/config.py` reads the root `.env`. Secrets use secret-valued settings and are never included in the health response. Add database readiness checks only when the database integration exists.
