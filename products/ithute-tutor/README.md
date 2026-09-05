# !thute Tutor

`!thute Tutor` is a first-party Ithute Solutions product hosted at:

```text
https://tutor.ithute.co.ls
```

It is a multi-tenant school management platform. Tutor owns its school, learner, teacher, parent, finance, staff and academic data in a dedicated PostgreSQL database. Identity and device notification delivery are shared Ithute platform services.

## Platform boundaries

```text
Browser / future mobile app
          |
          v
https://tutor.ithute.co.ls
          |
     +----+--------------------+
     |                         |
     v                         v
Tutor Next.js             Tutor FastAPI
frontend                  backend
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
       Tutor PostgreSQL   !thute Auth       !thute Push
       ithute_tutor DB    central identity  central delivery
                         auth.ithute.co.ls  push.ithute.co.ls
```

The boundaries are intentional:

- **Tutor database:** schools, roles, students, teachers, parents, classes, grades, attendance, fees, payroll, Tutor notifications and all other Tutor business records.
- **!thute Auth:** account credentials, MFA/passkeys, central sessions, JWT signing keys and the immutable cross-product `sub` identity.
- **!thute Push:** device/provider endpoints, queueing, retries and delivery receipts.
- Tutor never receives the Auth database password or JWT private key.
- Tutor never reads the Push database or calls FCM/APNs directly.

## Current product modules

The imported school system already contains substantial functionality, including:

- multi-school / tenant data models;
- school administrators, principals and vice-principals;
- students, teachers, parents and employee records;
- grades, classes, subjects and enrolments;
- student attendance and attendance KPIs;
- school fee configuration and fee plans;
- invoices, payments, allocations and student credit;
- employee salary/payroll/payment models;
- M-Pesa integration code;
- local in-app notifications;
- WebSocket live events;
- social feed models;
- Next.js management dashboards.

This integration work preserves those product capabilities while moving shared identity and push concerns to the central Ithute platform.

## Central Auth status

Central Auth already registers the first-party client ID:

```text
ithute-tutor
```

Tutor now validates central access tokens using:

```text
issuer    = https://auth.ithute.co.ls
audience  = ithute-tutor
algorithm = RS256
token_use = access
identity  = sub
```

Signing keys are resolved through central JWKS. The Tutor backend accepts the access token either as a Bearer token or from the Tutor HttpOnly access cookie used by the browser flow.

### Browser SSO

Tutor uses OpenID Connect Authorization Code + PKCE (`S256`).

The production callback is:

```text
https://tutor.ithute.co.ls/api/auth/oidc/callback
```

Normal flow:

1. User opens Tutor and chooses **Continue with !thute**.
2. Tutor generates PKCE verifier/challenge, `state` and `nonce`.
3. Browser is redirected to `https://auth.ithute.co.ls/oauth/authorize`.
4. Central Auth authenticates the user.
5. Auth redirects the one-time code to Tutor's exact callback.
6. Tutor verifies `state`, exchanges the code with the original verifier and validates the ID/access tokens against central JWKS.
7. Tutor stores the central refresh token only in an HttpOnly cookie.
8. Tutor resolves the central `sub` against its own local `users.auth_user_id`.

### Product authorization remains local

`!thute Auth` answers **who the user is**.

Tutor still answers **what that user may do**. Roles such as `school_admin`, `teacher`, `student`, `parent`, `bursar`, `principal`, etc. and school membership remain in the Tutor database.

### Existing user migration

The Tutor `users` table now has:

```text
auth_user_id UUID NULL UNIQUE
```

It is deliberately nullable during migration.

Existing users are **not** linked by matching email, phone or display name. An existing account is linked only after the user proves both identities:

1. successfully signs into central `!thute Auth`; and
2. supplies the existing Tutor email/password once on the link screen.

The old Tutor password login endpoint is disabled by default with:

```text
ITHUTE_TUTOR_LEGACY_AUTH_ENABLED=false
```

The legacy password column remains temporarily for safe account linking and migration. It can be removed in a later schema cleanup after all required accounts have been migrated.

## Central Push status

Tutor has a backend client for central `!thute Push`.

The backend obtains a short-lived service token from central Auth using:

```text
client_id = ithute-tutor
audience  = ithute-push
scope     = push.send
token_use = service
```

It then publishes messages to:

```text
POST https://push.ithute.co.ls/v1/messages
```

In the combined Docker network, backend-to-platform calls use the internal service addresses while JWT issuer validation remains the public `https://auth.ithute.co.ls` issuer.

The Push client supports recipient central `sub`, title, body, route, data, TTL and `Idempotency-Key`.

**Important:** the imported Tutor system already has local channel notifications and WebSocket events. Central Push is now available as the product delivery transport, but each business event still needs an explicit recipient policy before it should generate a phone notification. Do not blindly push every internal finance/admin WebSocket event to every user.

## Database

Tutor has its own database service:

```text
tutor-db
PostgreSQL 16
DB name: ithute_tutor
```

Persistent volume:

```text
ithute_tutor_postgres
```

Generated student media is also separated into:

```text
ithute_tutor_media
```

Tutor must never use the Auth or Push database connection strings.

## Docker files

Tutor uses these files:

```text
docker-compose.ithute-tutor.yml
    Product DB + backend + frontend

docker-compose.ithute-tutor-prod.yml
    Standard production Nginx dependency override

docker-compose.ithute-tutor-caddy.yml
    Optional commercial Caddy dependency override

products/ithute-tutor/sms_back_end/Dockerfile
products/ithute-tutor/sms_back_end/docker-entrypoint.sh
products/ithute-tutor/sms-frontend/Dockerfile
```

The backend startup sequence is:

```text
wait for tutor-db
    -> alembic upgrade heads
    -> ensure auth_user_id schema/index exists
    -> run startup seed
    -> start FastAPI on :8000
```

The frontend builds as a production Next.js application and uses same-origin:

```text
/api
```

so the browser does not need a hard-coded backend host.

## Public routing

Production hostname:

```text
tutor.ithute.co.ls
```

Routing contract:

```text
/api/*    -> tutor-backend:8000 (with /api stripped)
/media/*  -> tutor-backend:8000
/*        -> tutor-frontend:3000
```

The WebSocket client therefore resolves to:

```text
wss://tutor.ithute.co.ls/api/ws/events
```

Both repository edge configurations contain the Tutor route:

- `infrastructure/nginx/default.conf`
- `infrastructure/caddy/bootstrap.sh`

Caddy provides the public HTTPS/TLS edge in the commercial deployment path. Nginx is the internal production proxy in the standard Ithute production compose topology.

## Health checks

Tutor backend exposes:

```text
GET /healthz
GET /readyz
GET /health/dependencies
```

`/healthz` checks process liveness.

`/readyz` requires:

- Tutor PostgreSQL connectivity; and
- central Auth JWKS availability.

Push is reported by `/health/dependencies` but does not make the whole school management system unready if a push provider has a temporary outage.

Frontend and database services have Docker health checks as well.

## Required environment

See both:

```text
/.env.example
/products/ithute-tutor/.env.example
```

Minimum Tutor production values:

```text
ITHUTE_TUTOR_DB_PASSWORD=<strong random password>
ITHUTE_TUTOR_PUBLIC_URL=https://tutor.ithute.co.ls
ITHUTE_TUTOR_FRONTEND_URL=https://tutor.ithute.co.ls
ITHUTE_TUTOR_OIDC_REDIRECT_URI=https://tutor.ithute.co.ls/api/auth/oidc/callback
ITHUTE_TUTOR_LEGACY_AUTH_ENABLED=false
ITHUTE_TUTOR_PUSH_SERVICE_CLIENT_SECRET=<unique random service secret>
```

Central Auth must contain the exact Tutor redirect:

```text
ITHUTE_AUTH_REDIRECT_URIS_JSON={"ithute-tutor":["https://tutor.ithute.co.ls/api/auth/oidc/callback"]}
```

and a matching service secret entry:

```text
ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON={"ithute-tutor":"<same Tutor service secret>"}
```

When other Ithute products are also present, preserve their entries in these JSON maps; do not replace the maps with Tutor-only production values.

## Optional first super-admin bootstrap

The old imported code contained a fixed local super-admin credential. That behavior has been removed.

For the first deployment, an already-existing central Auth account may be explicitly mapped as Tutor super-admin with:

```text
ITHUTE_TUTOR_BOOTSTRAP_AUTH_USER_ID=<central Auth sub UUID>
ITHUTE_TUTOR_BOOTSTRAP_ADMIN_EMAIL=<local Tutor profile email>
ITHUTE_TUTOR_BOOTSTRAP_ADMIN_USERNAME=superadmin
```

No known local password is generated or exposed. After the profile exists, the central Auth identity is authoritative.

If the old hard-coded administrator credential was ever used in a real environment, rotate that account credential and treat the old value as compromised.

## Standard production compose validation

The standard repository production topology should be composed with Tutor as an additional override, for example:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.phase6-mail.yml \
  -f docker-compose.phase11-backup.yml \
  -f docker-compose.phase12-monitoring.yml \
  -f docker-compose.ithute-platform.yml \
  -f docker-compose.ithute-tutor.yml \
  -f docker-compose.ithute-tutor-prod.yml \
  -f docker-compose.deploy.yml \
  config
```

The commercial Caddy deployment uses `docker-compose.ithute-tutor-caddy.yml` instead of the Nginx dependency override.

## Local diagnostic ports

The Tutor containers expose only loopback diagnostic ports by default:

```text
Frontend: 127.0.0.1:3202
Backend:  127.0.0.1:8202
```

These are not the production public addresses. Users access Tutor through `https://tutor.ithute.co.ls`.

## External work still required before production can be called live

Repository configuration cannot by itself complete these external steps:

1. Create/verify DNS for `tutor.ithute.co.ls` pointing to the production HTTPS edge.
2. Put strong Tutor DB and service credentials into runtime secrets/environment.
3. Keep the exact Tutor callback in the deployed central Auth redirect allowlist.
4. Put the same Tutor Push service secret into central Auth and Tutor runtime config.
5. Ensure central `!thute Auth` is healthy and its JWKS is reachable.
6. Ensure central `!thute Push` is healthy and its provider configuration (FCM for Android v1) is complete.
7. Run the Tutor database migration on the target database.
8. Smoke-test central SSO, existing-account linking, logout/refresh, school/role isolation and WebSockets.
9. Define the correct business recipients for each Tutor event before enabling broad mobile push notifications.

## Security rules

- Never commit production DB passwords, service-client secrets, Firebase service-account JSON or JWT private keys.
- Never link two users solely because their email/phone/name appears similar.
- Never let Tutor query the Auth database directly.
- Never let Tutor store central MFA/passkey credentials.
- Never let Tutor call Firebase directly.
- Keep school/role authorization in Tutor, not Auth.
- Keep `auth_user_id` immutable after a profile has been linked, except through an audited administrative recovery process.

## Current integration status

As of this branch:

- Tutor product directory is on the current repository baseline.
- dedicated Tutor PostgreSQL topology is configured;
- central Auth client registration exists;
- RS256/JWKS product token validation is implemented;
- OIDC Authorization Code + PKCE browser login is implemented;
- safe existing-account linking is implemented;
- central refresh/logout session handling is implemented;
- local password login is disabled by default;
- central Push service-token/message client is implemented;
- backend and frontend Dockerfiles are present;
- production Nginx and Caddy hostname routing is configured;
- liveness/readiness dependency checks are present;
- hard-coded imported administrator credentials were removed;
- generated build/cache files are excluded from future Docker contexts.

The next production milestone is **runtime deployment and acceptance testing**, not another identity redesign.
