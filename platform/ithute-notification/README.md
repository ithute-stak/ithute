# Ithute Notification

Ithute Notification is the shared multi-channel delivery gateway for Ithute products. It does not replace Ithute Push. It coordinates durable notification requests and delegates Push delivery to the existing Push platform while providing email and SMS adapters.

## Security boundary

Callers obtain a short-lived managed service JWT from Ithute Auth with:

- audience `ithute-notification`
- scope `notification.send`
- `service_auth=managed`

The request `source_client_id` must exactly match the authenticated service client. This prevents one integration from impersonating another product.

The initial platform clients created for the Business Digital Address prototype already have `notification.send` where appropriate. The Notification gateway itself is registered as a separate managed service client with audience `ithute-push` and scope `push.send.delegated`; it starts without a credential. A platform administrator must rotate its first secret and supply it through `NOTIFICATION_AUTH_CLIENT_SECRET` before Push delegation can work.

## API

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

Use `Idempotency-Key` for all business events. Reusing a key with identical content returns the existing notification; reusing it with different content fails with `409`.

`GET /v1/notifications/{notification_id}` returns aggregate and per-channel state.

## Delivery model

Each requested channel becomes an independent durable delivery row:

- `push` — obtains a short-lived `push.send.delegated` token from Ithute Auth and calls the existing Ithute Push platform API.
- `email` — delivers through the configured SMTP relay.
- `sms` — delivers through the configured SMS webhook/provider adapter.

The worker uses row locking and retry backoff. Provider attempts remain in one database transaction so a worker crash cannot leave a permanently stuck `processing` delivery. Push requests use their own stable idempotency key.

## Configuration

Required for API/worker:

- `NOTIFICATION_DATABASE_URL`
- `NOTIFICATION_AUTH_ISSUER`
- `NOTIFICATION_AUTH_JWKS_URL`

Required for Push delegation:

- `NOTIFICATION_AUTH_TOKEN_URL`
- `NOTIFICATION_AUTH_CLIENT_ID=ithute-notification`
- `NOTIFICATION_AUTH_CLIENT_SECRET`
- `NOTIFICATION_PUSH_URL`

Email:

- `NOTIFICATION_SMTP_HOST`
- `NOTIFICATION_SMTP_PORT`
- `NOTIFICATION_SMTP_USERNAME`
- `NOTIFICATION_SMTP_PASSWORD`
- `NOTIFICATION_SMTP_FROM`

SMS:

- `NOTIFICATION_SMS_WEBHOOK_URL`
- `NOTIFICATION_SMS_WEBHOOK_TOKEN`

## Business Digital Address usage

The future standalone Business Digital Address application should call this gateway after storing an official communication. For sensitive RSL/Trade notices the Push/SMS/email body should normally contain only a safe alert such as “You have a new official communication”; the confidential message remains inside the authenticated official inbox.
