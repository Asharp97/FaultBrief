# FaultBrief frontend

Next.js App Router application with a Tailwind/GSAP marketing homepage with a server-side session redirect and Neon SDK signup/login and password recovery, a protected workspace page with owner-controlled team access and a ticket/evidence/report dashboard, and server-side API proxies. The paper/teal visual direction and reduced-motion support carry into the account screens.

From the repository root, run `pnpm run setup`, `pnpm run auth:configure`, and `pnpm run dev`. Follow [the complete sign-in walkthrough](../docs/authentication.md) for Neon trusted origins, verification, and test accounts.

The frontend requires server-only `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET`, and `FAULTBRIEF_API_BASE_URL`. Actual values live in ignored `.env.local`; the database URL stays in `backend/.env`.

```sh
pnpm run build
pnpm run start
pnpm run typecheck
pnpm exec playwright install chromium
pnpm run test:e2e
```

Run those commands inside `frontend`. This is no longer an `out/` static export: deploy a Next.js server or compatible managed runtime. The homepage checks the session on the server: signed-in users go directly to the dashboard; signed-out visitors see the marketing UI. Auth and private routes also run on the server.

The marketing investigation samples use synthetic UI data. They do not run a model or claim a connected diagnostic worker. Browser tests use a loopback test provider/API; live Neon email/password testing uses your own development accounts.

## First investigation setup

Development workspace owners see a guided Ledger setup when no affected customers are connected. The command is scoped to their workspace/user, and **Refresh customers** reloads newly approved mappings. Team members and affected product customers are distinct. See [the model-free walkthrough](../docs/testing-first-investigation.md); the command is local operator setup, not a browser-accessible lab API.
