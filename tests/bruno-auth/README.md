# Neon authentication manual tests

Start the frontend and backend using [the authentication walkthrough](../../docs/authentication.md). Open this directory as a collection in Bruno, choose **Local**, and copy `.env.example` to ignored `.env`. Fill your own development account's email/password/name. Keep Bruno's cookie jar enabled. The Origin header must match `frontend_url` exactly, including port and without a trailing slash.

## Run in this order

| Requests | What they test                                                                                     | Setup                                                      |
| -------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 01       | Optional signup                                                                                    | Set `run_signup=true` only to create an account            |
| 02–07    | Login, session, JWT, authenticated application identity, logout, denied identity                   | Existing verified development account                      |
| 08–13    | Recovery email, password reset, new-password login, logout, token reuse and old-password rejection | Optional: changes your test password; read the steps below |
| 14–18    | Invalid token, missing Origin, external redirect, unavailable admin API, JWT without session       | Run after sign-out; no successful password change          |

If email verification is required, run 01 by itself, verify through your email, then continue at 02. Existing verified accounts can leave signup disabled. The JWT from 04 is captured as runtime `api_token`; before sign-out, copy it into the original API collection's ignored `tests/bruno/.env` as token A. Repeat with a different user for token B.

## Optional recovery test

Use a disposable account with an inbox you control. Requests 08–13 are skipped until `run_password_recovery=true`.

1. Finish 02–07 so the account is signed out. Set a **different**, valid `AUTH_TEST_NEW_PASSWORD` in ignored `.env`. Retain the old `AUTH_TEST_PASSWORD` for request 13.
2. Enable `run_password_recovery` and run **08 only**. Open the recovery email; its final application link has `?token=…`. Do not complete the reset in the browser if you want to exercise request 09.
3. Put the token value in `AUTH_RESET_TOKEN` in ignored `.env`; reload Bruno's environment if needed. Run 09–13 in order, then 14–18. Request 09 changes the password; 12 expects the spent token to fail and 13 expects the old password to fail.
4. Afterward, update `AUTH_TEST_PASSWORD` to the new password, clear `AUTH_RESET_TOKEN`, and disable `run_password_recovery` before rerunning 02–07. Request 09 cannot be rerun without a fresh email token. Never save reset tokens or passwords in tracked requests or exports.

These requests use the frontend at **http://localhost:3000**, not FastAPI port 8000. Provider email settings, trust configuration, and verification policy are managed in Neon. Copied API JWTs may remain valid until expiry after sign-out; 07 and 18 check cookie-authenticated access. The 18-request auth collection complements the 116 application API requests; team management lives in the latter's folder 09.
