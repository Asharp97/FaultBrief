# FaultBrief frontend

Static Next.js marketing page using Tailwind CSS, GSAP, and self-hosted open-source fonts. The visual direction adapts the supplied paper-and-teal reference to FaultBrief's support-investigation concept.

## Development

```sh
npm ci
npm run dev
```

## Verification and export

```sh
npm run typecheck
npm run build
```

The static production site is generated in `out/`. Serve that directory with a static host; it needs no serverless functions. `next start` is not used for a static export.

The three interactive investigations are prepared examples. They do not call AI APIs, access Neon, change settings, or imply a connected backend. Motion respects reduced-motion preferences; GSAP instances are cleaned up on unmount.

## Planned infrastructure

- Neon PostgreSQL for investigations, jobs, evidence, and workspace data. Free compute scales to zero and wakes on the next query.
- Python/FastAPI API plus a worker for live investigations. Neon being a serverless database does not require serverless application functions.
- An internal model-provider module initially; a separately hosted AI gateway is optional later.
- Private object storage when files or large artifacts are uploaded. Small runbooks and structured evidence can initially be stored in PostgreSQL.
- Authentication is a separate choice now that the database choice is Neon.
- Keep model-provider and database credentials on the backend.
- Continuous idle polling of a Neon-backed job table can keep database compute active; design worker signaling accordingly.

No domain, backend credentials, authentication, or production deployment has been configured by this frontend.
