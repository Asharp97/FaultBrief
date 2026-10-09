# Authentication and workspace access

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

## Recover a password

1. On the sign-in page, choose **Forgot your password?** (or visit `/auth/forgot-password`). Enter your own test account email.
2. The page uses the same confirmation for existing and unknown accounts. Neon sends the email; FaultBrief does not store a recovery token or send its own password emails.
3. Follow the email link to `/auth/reset-password`, enter a new password twice, and select **Update password**. Sign in with that password afterward.
4. Missing, invalid, expired, or already-used links cannot update a password. Request another link if needed. The page removes the token from the address bar, keeps it only in memory, and uses a no-referrer policy. Refreshing this page requires reopening the email link.

The frontend accepts recovery redirects only to its own reset page. Your deployed origin must be trusted in Neon. Confirm recovery-email delivery with your development account; automated tests use a synthetic mailbox. The SDK follows the [Better Auth recovery contract](https://www.better-auth.com/docs/authentication/email-password#request-password-reset). Neon controls token expiry, email delivery, and provider session revocation; the SDK proxy cannot set the managed provider's server-side policy. Copied API JWTs can remain valid until expiry.

## Add teammates and manage roles

1. Each teammate signs up and signs in, opens their dashboard, and selects **Copy my user ID**. This copies their local FaultBrief identity UUID.
2. The workspace owner chooses **View team for …**, enters the teammate's user ID, chooses a starting role, and selects **Add teammate**. The account must already be provisioned through the dashboard or `GET /v1/me` in the same authentication provider.
3. The owner can **Save role**, **Deactivate**, or **Reactivate** a membership. This is direct access provisioning for known teammates; email invitations and an account directory are future features.
4. To transfer ownership, first promote another teammate to owner, then demote the previous owner. The API rejects any change that would remove the last active owner, including concurrent requests.

| Role    | Read workspace data / leave feedback | Create customers and investigations | Configure integrations | Manage teammates |
| ------- | ------------------------------------ | ----------------------------------- | ---------------------- | ---------------- |
| Owner   | Yes                                  | Yes                                 | Yes                    | Yes              |
| Admin   | Yes                                  | Yes                                 | Yes                    | No               |
| Support | Yes                                  | Yes                                 | No                     | No               |
| Viewer  | Yes                                  | No                                  | No                     | No               |

Membership creation uses `POST /v1/workspaces/{workspace_id}/memberships`; changes use `PATCH /v1/workspaces/{workspace_id}/memberships/{membership_id}`. The dashboard calls the matching `/api/faultbrief/workspaces/…` proxy, including same-origin checks on PATCH. Every protected backend request reads current membership from PostgreSQL. Deactivation immediately prevents that workspace's reads and writes even if the user still has a valid JWT; it does not sign them out of other workspaces. Inactive rows preserve investigation/feedback history and can be reactivated; duplicate creation returns 409. No migration is needed for these operations because the existing membership table already stores roles and active flags.

## What calls what

| Operation                 | Browser / Bruno route on the frontend   | Owner                                      |
| ------------------------- | --------------------------------------- | ------------------------------------------ |
| Create account            | `POST /api/auth/sign-up/email`          | Neon SDK → Neon Auth                       |
| Sign in                   | `POST /api/auth/sign-in/email`          | Neon SDK → Neon Auth                       |
| Read session              | `GET /api/auth/get-session`             | Neon SDK, signed HTTP-only session cache   |
| Obtain JWT                | `GET /api/auth/token`                   | Neon Auth                                  |
| Sign out                  | `POST /api/auth/sign-out`               | Neon SDK → Neon Auth, cookie clearing      |
| Request recovery link     | `POST /api/auth/request-password-reset` | Neon Auth email delivery                   |
| Reset password            | `POST /api/auth/reset-password`         | Neon Auth validates the one-time token     |
| Verify email              | `GET /api/auth/verify-email`            | Neon Auth email link                       |
| Read application identity | `GET /api/faultbrief/me`                | Next.js sends JWT to FastAPI `GET /v1/me`  |
| Company workspaces        | `GET, POST /api/faultbrief/workspaces`  | Next.js sends JWT to FastAPI workspace API |

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

The browser tests run the real Neon SDK against a loopback provider/API double with synthetic credentials. They cover signup, invalid and valid sign-in, email-verification-required behavior, HTTP-only cookies, protected pages, authenticated workspace creation, cross-origin rejection, password recovery, teammate provisioning, role changes, last-owner protection, revocation, and sign-out. Existing backend tests exercise real signed JWT verification and PostgreSQL permissions. Neither automated suite creates real Neon users. Complete signup/sign-in and the recovery walkthrough with your own test account to validate live provider settings and email delivery. PostgreSQL tests also exercise simultaneous owner removals on independent connections.

Browser test artifacts are ignored. CI installs Chromium and runs the same browser checks without Neon credentials. The tests restore Next.js-generated type configuration after their temporary server stops.
