# !thute Auth ↔ !thute Push Integration

## Purpose

!thute Auth and !thute Push are independent central platform services. They must never share a database and products must never write directly into either service's tables.

The integration is based on three mechanisms:

1. RS256-signed JWTs issued by !thute Auth and verified by !thute Push through JWKS.
2. A dedicated short-lived Push resource token for signed-in users.
3. A durable Auth lifecycle outbox that propagates session/account/application revocation state to Push.

This architecture allows Push to continue verifying tokens locally while retaining immediate revocation state even during a temporary Auth outage.

## Trust boundaries

### !thute Auth owns

- central users and immutable `sub`
- authentication sessions and `sid`
- password, MFA and passkeys
- product client registration
- account/application enabled state
- service-token issuance
- signing keys/JWKS

### !thute Push owns

- provider endpoints/tokens (FCM, APNs and Web Push)
- encrypted endpoint storage
- device-to-user/application/session bindings
- notification messages and delivery attempts
- delivery/open acknowledgements
- persisted Auth lifecycle/revocation state

### Products own

- business data
- company/school membership
- product roles and authorization
- subscriptions/licensing
- notification business decisions

No service reads another service's database.

## Token classes

The token classes are intentionally non-interchangeable.

### Product user access token

Issued during login/OIDC and intended only for the product itself.

Typical claims:

```json
{
  "iss": "https://auth.ithute.co.ls",
  "sub": "USER_UUID",
  "aud": "ithute-tutor",
  "sid": "SESSION_UUID",
  "token_use": "access"
}
```

Push rejects this token.

### Push user access token

The product exchanges its live product access token at:

```text
POST /v1/auth/push-token
Authorization: Bearer <product-access-token>
```

Auth checks the product session, user and application in the Auth database, then issues a short-lived Push-only token:

```json
{
  "iss": "https://auth.ithute.co.ls",
  "sub": "USER_UUID",
  "aud": "ithute-push",
  "azp": "ithute-tutor",
  "sid": "SESSION_UUID",
  "scope": "push.device",
  "token_use": "push_access",
  "jti": "UUID"
}
```

Default lifetime: 3 minutes.

Push accepts this token only for user/device operations. Device registrations are bound to all three identifiers:

```text
sub + azp + sid
```

This means a revoked Auth session cannot continue managing or resurrecting a Push endpoint.

### Product service token

A product backend obtains a service token from:

```text
POST /v1/auth/service-token
```

with `audience=ithute-push` and `scope=push.send`.

Typical claims:

```json
{
  "iss": "https://auth.ithute.co.ls",
  "sub": "service:ithute-tutor",
  "aud": "ithute-push",
  "azp": "ithute-tutor",
  "scope": "push.send",
  "token_use": "service"
}
```

This token can queue notifications for that product. It cannot register devices or submit Auth lifecycle events.

### Auth lifecycle token

The Auth lifecycle worker signs its own token directly using the Auth signing key:

```json
{
  "iss": "https://auth.ithute.co.ls",
  "sub": "service:ithute-auth",
  "aud": "ithute-push",
  "azp": "ithute-auth",
  "scope": "push.lifecycle",
  "token_use": "service"
}
```

Push accepts this token only on the internal lifecycle endpoint. Product service tokens cannot call that endpoint.

## Device registration flow

```text
User
  │
  ▼
Product ── product access token ──► !thute Auth
  │                                  │
  │                         POST /v1/auth/push-token
  │                                  │
  ◄──────── Push-scoped token ───────┘
  │
  │ POST /v1/devices
  │ Authorization: Bearer <push_access>
  ▼
!thute Push
  │
  └── stores encrypted provider endpoint bound to:
      auth_user_id = sub
      application_id = azp
      auth_session_id = sid
```

Provider tokens are encrypted at rest in the Push database.

## Notification send flow

```text
Product backend
   │
   │ client id + service secret
   ▼
!thute Auth
   │
   └── short-lived aud=ithute-push / push.send service token
          │
          ▼
Product backend
   │
   │ POST /v1/messages
   ▼
!thute Push
   │
   ├── verifies Auth signature/JWKS locally
   ├── verifies product is not disabled
   ├── verifies recipient is not disabled
   ├── excludes revoked Auth sessions
   ├── selects active endpoints for the same product only
   └── queues provider deliveries
```

A product cannot send through another product's endpoint namespace.

## Auth lifecycle propagation

Auth lifecycle changes and their outbox records are committed in the same Auth database transaction.

The SQLAlchemy transaction hook emits events when:

- an Auth session becomes revoked
- an account becomes disabled/enabled
- an application becomes disabled/enabled

This covers API routes, browser admin operations, scripts and future code using the same ORM models.

Events are stored in `auth_event_outbox`. A separate worker reads undelivered events and POSTs them to:

```text
POST /v1/internal/auth-events
```

The worker uses `push.lifecycle`, retries failures with capped exponential backoff, and never removes an event because of a network failure.

## Lifecycle event contract

### Session revoked

```json
{
  "event_id": "UUID",
  "type": "session.revoked",
  "sub": "USER_UUID",
  "sid": "SESSION_UUID",
  "client_id": "ithute-tutor",
  "occurred_at": "2026-09-04T20:00:00Z",
  "details": {
    "reason": "password reset"
  }
}
```

Push stores the revoked `sid` permanently in revocation state and deactivates endpoints bound to that session.

### Account status

```json
{
  "event_id": "UUID",
  "type": "account.disabled",
  "sub": "USER_UUID",
  "occurred_at": "2026-09-04T20:00:00Z",
  "details": {"active": false}
}
```

`account.enabled` has the same shape with `active=true`.

### Application status

```json
{
  "event_id": "UUID",
  "type": "application.disabled",
  "client_id": "ithute-tutor",
  "occurred_at": "2026-09-04T20:00:00Z",
  "details": {"active": false}
}
```

`application.enabled` has the same shape with `active=true`.

## Delivery guarantees

The integration uses at-least-once event delivery deliberately.

### Durable outbox

A revocation cannot be committed in Auth without its outbox event being committed in the same database transaction.

### Idempotency

Push records every lifecycle `event_id` as a primary key. Re-delivery of the same event is accepted without applying the change twice.

### Out-of-order protection

Account/application state includes `changed_at`. Push applies a new status only when its `occurred_at` is equal to or newer than the state already stored.

Therefore an older retried `account.disabled` event cannot overwrite a newer `account.enabled` event.

### UTC timestamp invariant

All lifecycle ordering and revocation timestamps are normalized to timezone-aware UTC at the Push persistence boundary. This is enforced through a SQLAlchemy UTC datetime type rather than by individual endpoints.

This matters because PostgreSQL preserves timezone-aware timestamps, while SQLite normally returns `DateTime(timezone=True)` values as timezone-naive. The UTC normalization layer guarantees equivalent comparison semantics in both environments and prevents stale-event ordering from crashing or behaving differently between tests and production.

### Monotonic session revocation

Once a `sid` appears in `revoked_auth_sessions`, it remains revoked. A still-unexpired JWT for that session is rejected by Push.

## Re-enable behavior

Enabling an account or application clears the disabled-state barrier, but Push does **not** automatically reactivate old provider endpoints.

The product must obtain a fresh Push token from Auth and register the device again. This is intentional: re-enablement proves there is a current valid Auth session before notifications resume.

## Migration behavior

Push migration `0003_auth_lifecycle_integration` adds `auth_session_id` to endpoints and deactivates legacy endpoints that have no session binding.

After deployment, clients must re-register provider endpoints through the Push-scoped token flow. This is a deliberate security migration and prevents pre-integration endpoints from bypassing session revocation.

## Availability model

Push does not call Auth on every request.

It validates Auth JWTs locally using the JWKS cache and combines that cryptographic validation with its local lifecycle state.

Consequences:

- a temporary Auth outage does not automatically stop Push from validating already-issued tokens
- a temporary Push outage does not lose Auth revocation changes because they remain in the Auth outbox
- after Push returns, the Auth worker retries outstanding lifecycle events

## Required product integration

Every Ithute product that uses Push should implement the same two client paths.

### Signed-in client/device

1. Authenticate with !thute Auth.
2. Keep the product access token for the product API only.
3. Call `POST /v1/auth/push-token` when Push device access is needed.
4. Use the returned token only against !thute Push device/ack endpoints.
5. Refresh by exchanging a still-valid product session again; never store the Push token as a long-lived credential.

### Product backend

1. Keep the product's service secret server-side only.
2. Request a short-lived `push.send` service token from Auth.
3. Call Push `POST /v1/messages` with an `Idempotency-Key` for retryable business operations.
4. Never place the product service secret or service token in a browser/mobile client.

## Security invariants

The following are platform invariants and should be regression tested:

- Auth and Push have separate databases.
- A normal product access token is rejected by Push.
- A Push user token cannot send notifications.
- A product service token cannot register devices.
- A product service token cannot submit Auth lifecycle events.
- Only `azp=ithute-auth` with `push.lifecycle` can submit lifecycle events.
- A revoked `sid` cannot register/manage an endpoint even before its JWT expires.
- Disabled users cannot register/manage endpoints or receive newly queued messages.
- Disabled products cannot register devices or queue messages.
- A stale lifecycle event cannot roll account/application state backwards.
- Lifecycle/revocation timestamps compare identically across SQLite and PostgreSQL through UTC normalization.
- Re-enabling never silently revives old endpoints; fresh registration is required.
