# Neon signup/login manual tests

Start the frontend and backend using the [authentication walkthrough](../../docs/authentication.md). Open this collection in Bruno, select Local, and copy .env.example to ignored .env. Fill your own development test account's email/password/name. Keep Bruno's cookie jar enabled. The Origin header must match frontend_url exactly, including port and without a trailing slash.

Run 01–07 in order. Signup is skipped unless run_signup=true. If Neon requires verification, run only signup, verify through your email, then continue from 02. Existing verified users can leave signup disabled. Requests create sessions with Neon, so account creation is an explicit optional step. They never use your database password.

The JWT from 04 is captured in runtime variable api_token. Before sign-out, copy it from the response into the original API collection's ignored tests/bruno/.env as token A. Repeat with a different test user for token B. Never save JWTs or actual account credentials into tracked Bruno files or exports. API JWTs remain valid until expiry even after browser sign-out; 07 checks cookie-authenticated access only.

Auth operations use frontend_url (port 3000), not the FastAPI Swagger base URL (8000). Provider admin routes are intentionally unavailable. These requests complement [the 86 application API tests](../bruno/README.md).
