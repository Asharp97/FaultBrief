# Architecture

## Implemented foundation

```mermaid
flowchart TD
    Launcher["Root development launcher"] --> Web["Next.js marketing preview :3000"]
    Launcher --> API["FastAPI foundation :8000"]
    Launcher --> Demo["Demo service foundation :8001"]
    API --> Settings["Validated backend-only environment settings"]
    Web --> Samples["Prepared synthetic investigation playback"]
```

The marketing samples are local UI playback. The API and demo expose separate liveness endpoints. There is no live connection between the samples, Neon, the demo service, or a model yet.

## Planned investigation runtime

```mermaid
flowchart TD
    User["Authenticated support engineer"] --> Dashboard["Private dashboard"]
    Dashboard --> API["Scoped backend API"]
    API --> DB["Neon: workspaces, jobs, evidence, reports"]
    DB --> Worker["Bounded investigation worker"]
    Worker --> Tools["Validated read-only diagnostic tools"]
    Tools --> Demo["Demo SaaS settings, jobs, and logs"]
    Tools --> Docs["Versioned runbook retrieval"]
    Worker --> Model["Reasoning model and optional tuned router"]
    Worker --> DB
```

The subscribing workspace and its affected customer are distinct scopes. The backend enforces both; the model cannot grant itself access. Model and database credentials stay on the server. Fine-tuning is a separate offline workflow, with model promotion based on evaluation.

Object storage, external AI gateways, and serverless application functions are optional additions when a concrete requirement justifies them.
