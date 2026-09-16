# Ithute Platform Mail Provisioning

The platform mail API is the machine-to-machine boundary between trusted Ithute products and the existing Ithute mail infrastructure.

It deliberately does **not** expose Postfix, Dovecot, Docker Mailserver configuration files, database credentials, or mailbox plaintext passwords to products such as Business Digital Address, Trade integrations, or RSL integrations.

## Authentication

Machine callers first obtain a short-lived RS256 service token from Ithute Auth. Mail provisioning requires:

- audience: `ithute-mail`
- scope: `mailbox.create`
- token type: `service`

The backend validates the token against Ithute Auth JWKS and never accepts a human access token for these endpoints.

## Domain grants

A service client cannot provision arbitrary domains merely because it has `mailbox.create`.

A platform owner must explicitly grant the service client access to each verified, mail-enabled domain:

- `POST /api/v1/platform/mail/domain-grants`
- `GET /api/v1/platform/mail/domain-grants`
- `POST /api/v1/platform/mail/domain-grants/{grant_id}/disable`

This prevents a future `trade-simulator`, for example, from creating an address under `ithute.co.ls` unless a platform owner deliberately grants that domain.

## Mailbox provisioning

`POST /api/v1/platform/mail/mailboxes`

Example request:

```json
{
  "external_reference": "2026/001234:official-address",
  "domain_name": "rsl-business.ls",
  "local_part": "tjekatjeka",
  "display_name": "Tjekatjeka Holdings (Pty) Ltd",
  "quota_bytes": 1073741824
}
```

The external reference is idempotent within the calling service client. Retrying the same request returns the existing binding instead of creating duplicate mailboxes. The same external reference cannot later be silently rebound to another email address.

## Credential boundary

Official platform-provisioned addresses are created in `platform-managed` credential mode.

Docker Mailserver still requires a Dovecot password hash, so Ithute generates a high-entropy internal credential and stores only the existing SHA512-CRYPT mailbox hash. The plaintext value is immediately discarded and is never returned by the platform API.

This is intentional: an RSL/Trade-facing product should authenticate people through Ithute Auth and expose the official inbox through its own authorized application experience rather than giving everyone a shared IMAP password.

## Ownership and lifecycle

Each platform-created mailbox has a binding to the service client and its external reference. One service client cannot inspect or mutate another client's bindings.

Current lifecycle endpoints are:

- `GET /api/v1/platform/mail/mailboxes/{binding_id}`
- `POST /api/v1/platform/mail/mailboxes/{binding_id}/suspend`
- `POST /api/v1/platform/mail/mailboxes/{binding_id}/reactivate`

Suspension is synchronized into Docker Mailserver, so a suspended address is removed from active mailbox authentication. Reactivation requires the original domain grant to still be active and the domain to remain verified and mail-enabled.

## Audit

Domain grants, provisioning, suspension, and reactivation are written to the existing Ithute audit log. Machine events include the Auth service client ID and JWT ID (`jti`) without storing service credentials.

## RSL / Trade prototype

The intended prototype sequence is:

1. a platform owner onboards or verifies the chosen official business domain;
2. the platform owner grants that domain to `business-digital-address` and/or `trade-simulator`;
3. Trade creates the business and uses Trusted Identity Invitations to activate its owner;
4. the Business Digital Address service requests `aud=ithute-mail`, `scope=mailbox.create`;
5. it provisions the permanent official address, such as `tjekatjeka@rsl-business.ls`;
6. the plaintext internal mailbox credential is never exposed to Trade, RSL, or the business owner.

Aliases, external-delivery verification, and an official `mail.send` delivery API are intentionally separate follow-up capabilities so provisioning remains small and auditable.
