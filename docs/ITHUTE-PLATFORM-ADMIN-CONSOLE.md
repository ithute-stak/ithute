# !thute Auth & Push superadmin console

## Location

The console is served in the Mailbox DNS panel at:

```text
https://panel.ithute.co.ls/ithute-platform
```

The browser communicates only with the Mailbox DNS backend BFF. It never receives:

- Auth private signing keys
- product service secrets
- `push.send` service tokens
- `push.lifecycle` tokens
- Push provider credentials
- FCM/APNs/WebPush endpoint tokens
- the temporary `push.admin` delegation token

## Authorization boundary

Central-platform administration is deliberately stronger than normal panel access.

A request must satisfy both identities:

1. The Mailbox DNS session belongs to a local `platform_owner`.
2. The owner is linked to the same immutable central Auth `sub` used by the !thute platform-admin session.
3. Central Auth confirms that the user is active and `is_platform_admin=true` through its live admin API.
4. Privileged elevation uses a fresh central password plus MFA/recovery-code challenge. Existing `ithute_sso` browser state does not bypass this step.

The panel stores the resulting central access token only in a Secure, HttpOnly, SameSite=Lax cookie scoped to `/api/v1/platform/ithute`. It does not retain the central refresh token. Elevation therefore expires and must be repeated.

## First-time legacy-owner binding

An older Mailbox DNS platform owner may not yet have `auth_user_id` populated.

The first successful privileged step-up may create this link only when:

- the local session is already a `platform_owner`;
- fresh central credentials pass;
- central MFA/recovery proof passes;
- Auth confirms the central account is a platform admin; and
- the central `sub` is not linked to another local panel account.

The link is written once and audited as `ithute.platform_admin.bootstrap_link`. Later step-ups must match the stored immutable `auth_user_id` exactly.

## Fresh admin authorization

The panel begins at:

```text
GET /api/v1/platform/ithute/admin/login
```

It generates cryptographically random OAuth `state`, `nonce` and PKCE verifier/challenge. The verifier and expected identities are stored in an HMAC-signed, HttpOnly state cookie.

The browser is redirected to the dedicated Auth endpoint:

```text
GET https://auth.ithute.co.ls/v1/admin/authorize
```

Unlike normal `/oauth/authorize`, this privileged endpoint always displays a fresh login form and requires MFA for platform admins. It validates the same exact client redirect allowlist and PKCE S256 rules as normal OIDC before creating an authorization code.

The code is exchanged server-side through:

```text
POST https://auth.ithute.co.ls/oauth/token
```

The panel verifies both access and ID tokens, checks the nonce, checks the linked subject, then calls:

```text
GET /v1/admin/overview
```

Auth remains authoritative for `is_platform_admin` and live session state.

## Push delegation

The panel never has a permanent Push admin credential.

For each Push administration request it asks Auth for:

```text
POST /v1/admin/push-token
```

Auth accepts that request only from a live `mailbox-dns` session belonging to an active platform admin. It mints a two-minute token with:

```json
{
  "aud": "ithute-push",
  "azp": "mailbox-dns",
  "sub": "HUMAN_AUTH_USER_UUID",
  "sid": "HUMAN_AUTH_SESSION_UUID",
  "scope": "push.admin",
  "token_use": "push_admin"
}
```

Push validates the exact token class and rejects product access, `push.device`, `push.send` and `push.lifecycle` tokens on `/v1/admin/*`.

Push also checks its local Auth lifecycle projection before serving the request. A revoked central admin session, disabled central account, or disabled Mailbox DNS application therefore removes Push admin access without requiring Push to query the Auth database.

## Dashboard data

The panel combines sanitized information from both services.

Auth overview includes:

- total/active users
- platform-admin count
- MFA-enabled and locked users
- active/revoked sessions
- active/total applications
- security-audit count
- pending Auth -> Push lifecycle outbox count

Push overview includes:

- total/active provider endpoints
- total and 24-hour message counts
- queued/no-endpoint messages
- delivered/opened/failed delivery counts
- received lifecycle event count
- revoked Auth session count
- disabled projected users/applications
- per-application endpoint/message aggregates
- recent notification metadata

Push never returns encrypted provider endpoint values from the admin API.

## Superadmin actions

The UI can:

- search central Auth users
- enable/disable a central user
- unlock a central user
- revoke a user's Auth sessions
- view Auth applications
- enable/disable a first-party application
- inspect Push delivery/application aggregates
- inspect recent Push message metadata

State-changing operations always go to Auth first. Auth writes its audit event and durable lifecycle outbox in its own transaction; Push then receives the lifecycle projection. The panel does not independently mutate Auth-owned state inside Push.

The Mailbox DNS BFF also records local audit entries for proxied user/application/session actions.

## Production environment

Use `docker-compose.ithute-admin.yml` with the normal platform compose files and configure values from `.env.ithute-admin.example`.

Important production values:

```text
ITHUTE_AUTH_ENABLED=true
ITHUTE_AUTH_ISSUER=https://auth.ithute.co.ls
ITHUTE_AUTH_AUDIENCE=mailbox-dns
ITHUTE_PLATFORM_AUTH_CALLBACK_URL=https://api.ithute.co.ls/api/v1/platform/ithute/admin/callback
ITHUTE_PLATFORM_PANEL_RETURN_URL=https://panel.ithute.co.ls/ithute-platform
ITHUTE_PLATFORM_PUSH_URL=http://ithute-push:8080
ITHUTE_PUSH_ALLOWED_ADMIN_CLIENTS=mailbox-dns
ITHUTE_PUSH_AUTH_MAX_ADMIN_TOKEN_SECONDS=180
```

The Auth redirect allowlist **must** contain the callback URL exactly under `mailbox-dns`. Merge it with existing Mailbox DNS callbacks instead of overwriting them. Example when it is the only callback:

```json
{
  "mailbox-dns": [
    "https://api.ithute.co.ls/api/v1/platform/ithute/admin/callback"
  ]
}
```

If production uses a different API hostname, change both `ITHUTE_PLATFORM_AUTH_CALLBACK_URL` and the Auth allowlist to the same exact HTTPS URL.

## Local validation

Run:

```bash
bash scripts/validate-ithute-admin-console.sh
```

It validates the Auth/Push foundation, both Python services, panel backend contract tests and the production Next.js build.

## Live acceptance gate

Before merge/deployment, test all of these against disposable PostgreSQL databases:

1. Sign into the normal panel as a platform owner.
2. Open `/ithute-platform`.
3. Complete fresh central platform-admin password + MFA authorization.
4. For a legacy unlinked owner, confirm the first step-up creates exactly one audited central link.
5. Confirm the Auth and Push dashboard loads without exposing tokens in browser responses or local storage.
6. Revoke another user's sessions and confirm the Auth outbox event reaches Push.
7. Disable an application and confirm its sessions/endpoints stop being usable.
8. Re-enable it and confirm old Push endpoints are not silently reactivated.
9. Revoke the current central admin session and confirm Push admin calls immediately fail after lifecycle projection.
10. End the elevated panel session and confirm `/platform/ithute/*` privileged requests require a new fresh step-up.
11. Confirm a non-owner, a non-platform-admin, and a platform admin without MFA are all denied.
