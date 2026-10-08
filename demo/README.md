# Demo application

This separate FastAPI service will host deliberately introduced customer failures. Its current implementation exposes only a liveness endpoint. It shares the backend's locked Python environment to avoid duplicate dependency stacks during the scaffold stage.

The next implementation adds customer roles, feature settings, job status, and bounded logs. Keep scenario setup and evaluation answer keys outside the investigator's accessible tools.

Start it together with the other services using `pnpm run dev` at the repository root.
