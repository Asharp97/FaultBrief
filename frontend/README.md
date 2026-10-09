# FaultBrief frontend

Next.js App Router application with a prerendered Tailwind/GSAP marketing homepage and Neon SDK signup/login and password recovery, a protected workspace page with owner-controlled team access, and server-side API proxies. The paper/teal visual direction and reduced-motion support carry into the account screens.

From the repository root, run `pnpm run setup`, `pnpm run auth:configure`, and `pnpm run dev`. Follow [the complete sign-in walkthrough](../docs/authentication.md) for Neon trusted origins, verification, and test accounts.

The frontend requires server-only `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET`, and `FAULTBRIEF_API_BASE_URL`. Actual values live in ignored `.env.local`; the database URL stays in `backend/.env`.

```sh
pnpm run build
pnpm run start
pnpm run typecheck
pnpm exec playwright install chromium
pnpm run test:e2e
```

Run those commands inside `frontend`. This is no longer an `out/` static export: deploy a Next.js server or compatible managed runtime. The homepage itself remains prerendered; auth and private routes run on the server.

The marketing investigation samples use synthetic UI data. They do not run a model or claim a connected diagnostic worker. Browser tests use a loopback test provider/API; live Neon email/password testing uses your own development accounts.
