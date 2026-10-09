# Signup, login, and API access

Neon Auth manages passwords, verification, and sessions. The browser calls the Neon SDK through the Next.js `/api/auth/*` proxy. FastAPI verifies the resulting JWT and checks local workspace membership. We added provider proxy routes; we did not build a second password system in FastAPI.

## Start locally

1. Keep your existing `DB_URL`, `AUTH_URL`, and `JWKS_URL` in `backend/.env`.
2. From the repository root, run `pnpm run setup`, `pnpm run auth:configure`, and `pnpm run db:migrate` if your development schema needs migration. The configuration helper reuses the backend Auth URL and creates a private cookie-signing secret in ignored `frontend/.env.local`. It preserves existing settings and never prints credentials.
3. In Neon Console, open your branch's **Auth → Configuration**. Enable email/password sign-in and add `http://localhost:3000` as a trusted origin. Add `http://127.0.0.1:3000` only if you also use that address. Add the actual origin for custom development ports or deployment. Provider configuration remains a Neon Console setting, not a FaultBrief migration.
4. Run `pnpm run dev`. Restart after changing environment settings.
5. Visit `http://localhost:3000/auth/sign-up`. Enter your name, a real email you control, and a password of at least eight characters.
6. If Neon requires email verification, follow the email link and then sign in at `/auth/sign-in`. The form will not claim that an unverified account is signed in.
7. A successful sign-in opens `/dashboard`. The page connects your verified identity to `GET /v1/me`; create a company workspace to exercise `POST /v1/workspaces`.
8. Press **Sign out**. Visiting `/dashboard` again redirects to sign-in; the cookie-authenticated API proxy rejects requests without a valid session.

The [official Neon Next.js guide](https://neon.com/docs/auth/quick-start/nextjs) describes this SDK integration and provider configuration. Email delivery and verification policy are controlled by Neon.

## What calls what

| Operation                 | Browser / Bruno route on the frontend  | Owner                                      |
| ------------------------- | -------------------------------------- | ------------------------------------------ |
| Create account            | `POST /api/auth/sign-up/email`         | Neon SDK → Neon Auth                       |
| Sign in                   | `POST /api/auth/sign-in/email`         | Neon SDK → Neon Auth                       |
| Read session              | `GET /api/auth/get-session`            | Neon SDK, signed HTTP-only session cache   |
| Obtain JWT                | `GET /api/auth/token`                  | Neon Auth                                  |
| Sign out                  | `POST /api/auth/sign-out`              | Neon SDK → Neon Auth, cookie clearing      |
| Verify email              | `GET /api/auth/verify-email`           | Neon Auth email link                       |
| Read application identity | `GET /api/faultbrief/me`               | Next.js sends JWT to FastAPI `GET /v1/me`  |
| Company workspaces        | `GET, POST /api/faultbrief/workspaces` | Next.js sends JWT to FastAPI workspace API |

The FastAPI Swagger document describes `/v1/*`; it does not list the separate Next.js provider proxy routes. Auth proxy operations are allowlisted; provider admin APIs are not exposed. POSTs require a matching browser Origin. API destinations come from server configuration, not user-supplied URLs. Workspace roles stay authoritative in PostgreSQL, not in browser forms or JWT role claims.

## Testing with Bruno

Open [the provider-flow collection](../tests/bruno-auth/README.md) first to test sign-in, session/JWT retrieval, authenticated API access, and sign-out. It uses the frontend base URL and Bruno's cookie jar. Use real test accounts; optional signup creates accounts in your configured Neon branch.

Alternatively, sign in through the dashboard and press **Copy API token for Bruno**. Paste that JWT into the ignored `tests/bruno/.env` for the original FastAPI collection. Sign in as a different user to obtain token B. Tokens expire; copy fresh ones when needed. JWTs are not passwords or opaque session tokens.

No credentials or JWTs are saved to localStorage or sessionStorage. The copy button places a JWT on your clipboard only when requested. Provider cookies are HTTP-only and use SameSite protection. FastAPI still verifies the JWT on every protected call; signing out clears the app's session but does not revoke an already copied JWT before its expiry.

## Configuration and deployment

`frontend/.env.local` needs `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET` (32+ characters), and `FAULTBRIEF_API_BASE_URL`. These are server-only settings: never prefix them with `NEXT_PUBLIC_`. In production, generate an independent cookie secret, use HTTPS, and point the API base URL at the deployed backend. Keep the backend's Auth URL, issuer, and JWKS consistent with the same Neon branch.

The frontend now requires a **Next.js Node server / compatible server deployment**, using `pnpm --dir frontend build` and `pnpm --dir frontend start`. Static-only `out/` hosting cannot handle sign-in cookies or API routes. The public marketing homepage remains prerendered. The dev launcher routes the frontend to the selected API port, including custom ports.

## Verification

```sh
pnpm --dir frontend exec playwright install chromium
pnpm run frontend:e2e
pnpm run check
```

The browser tests run the real Neon SDK against a loopback provider/API double with synthetic credentials. They cover signup, invalid and valid sign-in, email-verification-required behavior, HTTP-only cookies, protected pages, authenticated workspace creation, cross-origin rejection, and sign-out. Existing backend tests exercise real signed JWT verification and PostgreSQL permissions. Neither automated suite creates real Neon users. Complete steps 5–8 with your own test account to validate live provider settings and email delivery.

Browser test artifacts are ignored. CI installs Chromium and runs the same browser checks without Neon credentials. The tests restore Next.js-generated type configuration after their temporary server stops.
