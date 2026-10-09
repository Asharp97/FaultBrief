# Authentication: Neon Auth and FaultBrief

There are two services in the sign-in flow: **Neon Auth authenticates a person**, and **FaultBrief verifies that person's token and workspace permissions**.

## The intended flow

1. A person signs up or signs in through the configured Neon Auth provider using its client SDK.
2. The authenticated client obtains a signed JWT from Neon Auth.
3. The client sends that JWT to FaultBrief as `Authorization: Bearer <token>`.
4. FaultBrief verifies the signature, issuer, expiry, and required claims using the configured public keys. It then reads active memberships and roles from its own database to decide what the person can access.

Neon's [managed-token guidance](https://neon.com/docs/compute/functions/authentication) describes obtaining a short-lived token with `authClient.token()` and sending it as a bearer token.

## What is implemented

- The backend verifies JWTs and rejects missing or invalid authentication.
- `GET /v1/me` provisions or reads the local FaultBrief identity for an already authenticated person. It does **not** sign someone in or create a Neon account.
- Protected `/v1` endpoints check active workspace membership and the local role.
- Neon owns its users, credentials, and sessions; FaultBrief stores the verified identity's issuer/subject and local workspace relationships.

Adding `DB_URL`, `AUTH_URL`, and `JWKS_URL` to `backend/.env` configures the database connection and token verifier. It does not automatically create login pages or add provider endpoints to FaultBrief's OpenAPI document.

## What is still missing

The browser signup/login flow and Neon client integration have not been built yet. There are no FaultBrief `/login`, `/signup`, or `/logout` routes. Provider-owned operations would run against Neon Auth, not the FaultBrief API base URL.

The next authentication milestone is to wire the configured Neon SDK into signup/login and session handling, obtain JWTs for API requests, and add separate provider-flow tests. We do not need to implement a second password database in FaultBrief.

## Why Bruno does not have login requests yet

The [current Bruno collection](../tests/bruno/README.md) covers the implemented **FaultBrief** endpoints. Folder **02 Identity** checks an existing JWT, stable local identity, distinct users, and missing/malformed-token rejection.

Those tests assume you already obtained test-user JWTs from Neon. They cannot yet take an email/password and obtain a token. That is a real gap in the current end-to-end sign-in workflow, not a hidden FaultBrief endpoint. Keep the token-issuing provider requests separate from the application API requests when that milestone is implemented.
