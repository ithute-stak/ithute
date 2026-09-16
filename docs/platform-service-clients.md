# Ithute Auth managed platform service clients

Ithute Auth now distinguishes human/interactive OAuth applications from machine-to-machine platform identities.

Managed service clients are stored in the Auth database. Their plaintext secrets are never stored: Auth stores only a SHA-256 digest of a high-entropy generated secret plus a short display prefix. A plaintext secret is returned only when a client is created or a secret is rotated.

## Initial platform clients

The migration provisions three identities without credentials:

- `business-digital-address`
  - audiences: `ithute-auth`, `ithute-mail`, `ithute-dns`, `ithute-notification`
  - scopes: `identity.invite`, `mailbox.create`, `mail.send`, `dns.verify`, `notification.send`
- `trade-simulator`
  - audiences: `ithute-auth`, `ithute-mail`, `ithute-notification`
  - scopes: `identity.invite`, `mailbox.create`, `notification.send`
- `rsl-simulator`
  - audiences: `ithute-mail`, `ithute-notification`
  - scopes: `mail.send`, `notification.send`

They deliberately start without a usable secret. A platform administrator must rotate a secret before a client can request a token.

## Administration API

All endpoints below require an authenticated Ithute platform administrator.

- `GET /v1/admin/service-clients`
- `POST /v1/admin/service-clients`
- `PATCH /v1/admin/service-clients/{client_id}`
- `POST /v1/admin/service-clients/{client_id}/rotate-secret`
- `POST /v1/admin/service-clients/{client_id}/credentials/{credential_id}/revoke`
- `GET /v1/admin/service-clients/{client_id}/audit`

Creation returns the first secret once. Secret rotation returns the replacement secret once. With `revoke_previous=true` (the default), rotation immediately revokes every older active credential for that client.

A service client can also be disabled or assigned an expiry. Individual credentials can have their own expiry and can be revoked without disabling the entire identity.

## Token endpoint

Managed clients request a short-lived RS256 service JWT from:

`POST /v1/auth/service-token`

Example request shape:

```json
{
  "client_id": "trade-simulator",
  "client_secret": "<one-time-returned-secret>",
  "audience": "ithute-auth",
  "scope": "identity.invite"
}
```

Auth validates all of the following before issuing the JWT:

1. the managed client exists and is active;
2. the managed client has not expired;
3. the presented credential exists, is not revoked and has not expired;
4. the requested audience is in the client's explicit audience allow-list;
5. every requested scope is in the client's explicit scope allow-list.

Successful and failed token requests are written to the central Auth audit log, including the client ID, requested audience and scope. The plaintext secret is never written to audit history.

## Legacy compatibility

`AUTH_SERVICE_CLIENT_SECRETS_JSON` remains temporarily supported only for existing first-party integrations that do not yet have a row in `managed_service_clients`. If a managed client exists for a `client_id`, the database-managed identity takes precedence and the environment-secret fallback is not used.

The compatibility path should be removed after the remaining production integrations have migrated.
