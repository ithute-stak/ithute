# Ithute Notification

> **Production status: intentionally deferred.**
>
> As of **2026-09-16**, Ithute Notification is **not a required production dependency**. Ithute Auth and the Ithute Mail / Mail Provisioning platform are the current priority and can operate without this service. The Notification Gateway, Push delegation, SMS delivery, and notification retry/delivery tracking must remain optional until the activation checklist in this document has been completed.

Ithute Notification is the shared multi-channel delivery gateway for Ithute products. It does not replace Ithute Push. It coordinates durable notification requests and delegates Push delivery to the existing Push platform while providing email and SMS adapters.

## Why these features are not working in production yet

The Notification Gateway code exists, but the service has deliberately **not been activated in the production Compose/Caddy runtime yet**. This was a safety decision: the Auth and Mail foundations are enough for the first Business Digital Address version, and an unfinished notification integration must never be allowed to make Auth, Mail, DNS, or the main Ithute website unhealthy.

The following items are therefore expected to be unavailable until a future activation phase:

- **Notification Gateway API** — not yet provisioned as a live production service/container.
- **Notification Push delegation** — the `ithute-notification` managed service client exists conceptually, but its first production credential must be generated/rotated by a platform administrator and securely configured before it can request `push.send.delegated` tokens.
- **SMS notifications** — no production SMS provider/webhook credentials have been selected and configured yet.
- **Notification email channel** — this adapter still needs its own production SMTP configuration. This does **not** mean normal Ithute Mail is unavailable; the Mail platform is a separate subsystem and can continue handling official business email independently.
- **Notification retries and delivery tracking** — the durable queue/worker model is implemented as part of this service, but it only becomes operational after the Notification database, API, and worker are deployed and kept healthy in production.
- **Public Notification hostname/routing** — no production Caddy/DNS exposure should be added until the service identity, database, providers, health checks, and rollback path are ready.

This state is intentional. It should not be treated as a production incident while Auth and Mail are healthy.

## What works without Ithute Notification

The first Business Digital Address implementation can proceed with:

```text
Business registration / Trade integration
                |
                v
          Ithute Auth
   owner invitation + activation
                |
                v
      Business Digital Address
                |
                v
      Ithute Mail Provisioning
  official mailbox / official email
```

This is enough to register/invite the business owner, let the owner create and secure their Ithute identity, provision an official business mailbox/address, and send/receive official email.

Push and SMS are convenience/attention channels. They are **not the source of truth** for official RSL/Trade messages. Sensitive content should remain in the authenticated official inbox or official mailbox.

## Important distinction: Mail vs Notification email

Do not disable or postpone the Ithute Mail platform because this Notification Gateway is deferred.

```text
Ithute Mail
- official mailbox provisioning
- normal business email
- official email transport
- required for the first usable version

Ithute Notification
- short alert emails
- SMS alerts
- Push alerts
- retry/delivery state for alerts
- optional for the first usable version
```

For example, RSL can send an official communication through the official mailbox now. Later, Ithute Notification may additionally send a safe alert such as:

> You have received a new official communication. Sign in to view it securely.

The alert must not contain confidential tax/business content that belongs inside the authenticated inbox.

## Security boundary

Callers obtain a short-lived managed service JWT from Ithute Auth with:

- audience `ithute-notification`
- scope `notification.send`
- `service_auth=managed`

The request `source_client_id` must exactly match the authenticated service client. This prevents one integration from impersonating another product.

The initial platform clients created for the Business Digital Address prototype have `notification.send` only where appropriate. The Notification gateway itself uses a separate managed service client with audience `ithute-push` and scope `push.send.delegated`.

The gateway must start **without a default/shared plaintext secret**. A platform administrator must explicitly create/rotate its first credential when production activation is approved.

## API design

`POST /v1/notifications`

Example:

```json
{
  "source_client_id": "business-digital-address",
  "recipient_sub": "00000000-0000-0000-0000-000000000001",
  "recipient_email": "owner@example.com",
  "recipient_phone": "+26662000000",
  "channels": ["push", "email", "sms"],
  "title": "New official RSL communication",
  "body": "A new official communication is available in your business inbox.",
  "route": "/official-inbox/messages/example",
  "data": {"classification": "official"}
}
```

Use `Idempotency-Key` for business events. Reusing a key with identical content returns the existing notification; reusing it with different content fails with `409`.

`GET /v1/notifications/{notification_id}` returns aggregate and per-channel state.

## Delivery model

Each requested channel becomes an independent durable delivery row:

- `push` — obtains a short-lived `push.send.delegated` token from Ithute Auth and calls the existing Ithute Push platform API.
- `email` — delivers through the configured SMTP relay.
- `sms` — delivers through the configured SMS webhook/provider adapter.

The worker uses row locking and retry backoff. Provider attempts are recorded durably so failures can be retried without silently losing the notification. Push requests use their own stable idempotency key.

## What must be done before production activation

Do **not** simply add `ithute-notification` to production Compose and hope that providers are ready. Complete the following activation sequence:

1. Merge and validate the Notification Gateway implementation with Notification, Auth, Push, Realtime, Production Safety, and Standalone CI green.
2. Create a dedicated production PostgreSQL database/service for `ithute-notification` and run its Alembic migration in a disposable/smoke environment first.
3. Generate/rotate the first `ithute-notification` managed-service credential in Ithute Auth; store the secret only in the protected production secret/runtime configuration.
4. Configure `NOTIFICATION_AUTH_TOKEN_URL`, `NOTIFICATION_AUTH_CLIENT_ID=ithute-notification`, `NOTIFICATION_AUTH_CLIENT_SECRET`, and `NOTIFICATION_PUSH_URL`.
5. Verify Ithute Push accepts the managed `ithute-notification` client only for `push.send.delegated` and never grants broader Push/admin access.
6. Choose and configure the production SMS provider; set `NOTIFICATION_SMS_WEBHOOK_URL` and its protected token/credential.
7. Configure the Notification email adapter with dedicated SMTP settings and test it independently from the normal Mail Provisioning flow.
8. Start Notification API + worker on an internal network first. Confirm `/healthz`, `/readyz`, migrations, queue processing, retries, idempotency, and failed-provider behavior.
9. Run an end-to-end test for each channel separately, then a three-channel notification and verify per-channel delivery state.
10. Add production Compose/Caddy/DNS routing only after the internal service is healthy. The public route is optional; internal service-to-service access is preferred where possible.
11. Extend production deployment safety/rollback checks so a Notification failure cannot stop Auth, Mail, Web, DNS, Push, or Realtime.
12. Only then make Business Digital Address depend on the gateway for alerts. Official message storage/delivery must still succeed even when the Notification Gateway is temporarily unavailable.

## Production configuration when activated

Required for API/worker:

- `NOTIFICATION_DATABASE_URL`
- `NOTIFICATION_AUTH_ISSUER`
- `NOTIFICATION_AUTH_JWKS_URL`

Required for Push delegation:

- `NOTIFICATION_AUTH_TOKEN_URL`
- `NOTIFICATION_AUTH_CLIENT_ID=ithute-notification`
- `NOTIFICATION_AUTH_CLIENT_SECRET`
- `NOTIFICATION_PUSH_URL`

Email alert adapter:

- `NOTIFICATION_SMTP_HOST`
- `NOTIFICATION_SMTP_PORT`
- `NOTIFICATION_SMTP_USERNAME`
- `NOTIFICATION_SMTP_PASSWORD`
- `NOTIFICATION_SMTP_FROM`

SMS alert adapter:

- `NOTIFICATION_SMS_WEBHOOK_URL`
- `NOTIFICATION_SMS_WEBHOOK_TOKEN`

## Future Business Digital Address usage

When activation is complete, the standalone Business Digital Address application should call this gateway **after the official communication has already been stored successfully**.

Correct order:

```text
RSL / Trade message
       |
       v
Store official communication
       |
       +---- success ----> official inbox / official mailbox
                              |
                              v
                    request optional alerts
                      /       |       \
                   Push      SMS     Email
```

A Notification provider failure must never roll back or delete the official communication.

## Resume point for the next implementation session

When work on notifications resumes, start here:

1. Check the current state of PR **#179 — Add Ithute Notification Gateway** and reconcile it with the latest `main`.
2. Run all current CI from the latest head; do not trust older green/red runs attached to previous commits.
3. Keep production activation separate from service-code merge.
4. Confirm Auth and Mail remain healthy before and after every Notification deployment change.
5. Activate one channel at a time: **email alert → Push → SMS → combined delivery/retry reporting**.

Until that work is intentionally resumed, **Auth + Mail are the required production foundation; Notification/Push/SMS alerts are deferred enhancements.**
