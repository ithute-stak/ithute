# !thute Auth ↔ !thute Push Security Guarantees

This document defines the security and operational guarantees for the central identity-to-notification boundary. The detailed protocol is in `ITHUTE-AUTH-PUSH-INTEGRATION.md`.

## Non-negotiable trust boundaries

- !thute Auth and !thute Push have separate PostgreSQL databases.
- Products never write directly to either central database.
- Push never accepts a normal product access token for device operations.
- Auth issues a dedicated `aud=ithute-push`, `token_use=push_access`, `scope=push.device` token for signed-in device operations.
- Product backends use a separate `token_use=service`, `scope=push.send` token.
- Auth lifecycle delivery uses only `azp=ithute-auth`, `sub=service:ithute-auth`, `scope=push.lifecycle`.
- No product service token can submit lifecycle events.

## Strict JWT boundary

Push validates Auth tokens against the Auth JWKS and requires the expected issuer and exact `ithute-push` audience. It also requires the claim set appropriate to each token class, including `iat`, `nbf`, `exp` and `jti`.

Push additionally enforces:

- UUID-shaped `sub` and `sid` for Push user tokens.
- `sub=service:<azp>` for product service tokens.
- `sub=service:ithute-auth` and `azp=ithute-auth` for lifecycle tokens.
- short maximum token lifetimes independent of Auth configuration.
- bounded clock skew.

These checks protect Push even if a future Auth change accidentally mints a validly signed token with an overly broad or incorrect claim shape.

## Session binding

Every active provider endpoint is bound to:

```text
sub + azp/application + sid
```

A session revocation is monotonic. Once Push records a `sid` as revoked, that session cannot register or reactivate a provider endpoint even if its JWT has not expired.

Legacy endpoints without `sid` are deactivated by the lifecycle migration and must be registered again through a current Push-scoped token.

## Durable lifecycle propagation

Auth writes lifecycle changes and durable outbox records in the same database transaction. The worker uses at-least-once delivery and Push deduplicates by immutable event UUID.

The worker uses a short database lease:

1. lock one due outbox row with `FOR UPDATE SKIP LOCKED`;
2. move `next_attempt_at` into the future as a crash-safe lease;
3. commit immediately, releasing the database lock;
4. perform the HTTP request with no row lock held;
5. mark delivered, or schedule capped exponential backoff.

This permits multiple worker replicas and avoids holding PostgreSQL row locks during network I/O. If a worker dies after claiming a row, the event becomes eligible again after the lease expires.

## Lifecycle receiver safety

Push accepts only these lifecycle event types:

- `session.revoked`
- `account.disabled`
- `account.enabled`
- `application.disabled`
- `application.enabled`

The request schema enforces exact identifier shapes for each event class, timezone-aware timestamps, a bounded future clock window, and a size limit on event details.

Account/application updates use event time ordering so a delayed stale event cannot roll newer state backwards. Session revocation is monotonic and never undone by an enable event.

Re-enabling an account or application clears only the disabled-state barrier. Old provider endpoints remain inactive and require a current Auth session to register again.

## Failure model

### Auth temporarily unavailable

Push can continue validating already-issued tokens using cached JWKS keys, subject to token expiry and its persisted lifecycle state. New token exchange and new service-token issuance are unavailable until Auth returns.

### Push temporarily unavailable

Auth lifecycle events remain in the durable outbox. The worker retries after Push returns. No network failure marks an event delivered.

### Lifecycle worker crash

Claimed events become retryable when their lease expires.

### Duplicate delivery

Lifecycle `event_id` is the idempotency key. A duplicate event is accepted without applying state twice.

### Provider outage

Push delivery workers retry according to provider retry policy and never report a fake success.

## Backup and restore rule

Auth and Push remain separately backed up, but lifecycle state creates an ordering requirement during disaster recovery.

After an independent Push database restore, operators must not assume its local revocation projection is current merely because Auth outbox rows were already marked delivered before the restore point. The safe recovery procedure is:

1. restore Auth and Push data;
2. keep public Push traffic gated;
3. reconcile or replay lifecycle state from a point no later than the Push restore point;
4. verify disabled applications/users and revoked active sessions;
5. require fresh endpoint registration where state cannot be proven current;
6. reopen Push traffic.

Until an automated full-state reconciliation protocol is introduced, an independent Push restore should be treated as a security-sensitive recovery event, not a normal restart.

## Operational metrics to monitor

Production monitoring should expose or derive at least:

- undelivered Auth outbox event count;
- oldest undelivered event age;
- lifecycle delivery failures/retries;
- Push lifecycle endpoint 4xx/5xx rate;
- count of revoked-session rejections;
- count of disabled-account/application rejections;
- provider delivery failure rate;
- endpoints with missing session binding (expected to remain zero after migration/re-registration).

## Deployment policy

Recommended production values:

```text
AUTH_PUSH_USER_TOKEN_MINUTES=3
AUTH_SERVICE_TOKEN_MINUTES=5
AUTH_PUSH_EVENT_REQUEST_TIMEOUT_SECONDS=5
AUTH_PUSH_EVENT_LEASE_SECONDS=30
PUSH_AUTH_CLOCK_SKEW_SECONDS=30
PUSH_AUTH_MAX_PUSH_ACCESS_SECONDS=600
PUSH_AUTH_MAX_SERVICE_TOKEN_SECONDS=600
```

The Push lifetime ceilings intentionally remain somewhat above the standard Auth issuance lifetimes so normal configuration changes do not break the platform while still preventing unexpectedly long-lived bearer tokens from being accepted.
