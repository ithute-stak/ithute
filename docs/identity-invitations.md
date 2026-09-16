# Trusted identity invitations

Ithute Auth supports a trusted provisioning flow for external Ithute products and future government integrations without allowing those systems to choose or learn a person's password.

## Trust boundary

Only a database-managed service client with:

- audience `ithute-auth`; and
- scope `identity.invite`

may create, inspect, resend or cancel an invitation.

Legacy `AUTH_SERVICE_CLIENT_SECRETS_JSON` clients cannot call these endpoints.

## Flow

1. A trusted service requests a short-lived service token from `POST /v1/auth/service-token`.
2. It creates an invitation with `POST /v1/platform/identity-invitations` and a stable `external_reference` such as `2026/001234:owner`.
3. Ithute normalizes the phone/email, records the pending invitation and generates a one-time activation challenge.
4. The challenge is delivered directly to the registered owner through the configured SMS or email delivery channel. The plaintext challenge is never returned to the calling service and is not stored in the database.
5. The owner opens `/account/activate`, verifies the one-time challenge and, only for a brand-new Ithute identity, creates their own password.
6. If the contact already belongs to an Ithute user, the invitation links to that existing identity and does not replace the existing password.
7. Auth records the activation and emits `identity.invitation_activated` through its durable Auth event outbox.

## Platform endpoints

All require a managed `identity.invite` service token and are restricted to invitations owned by the calling service client.

- `POST /v1/platform/identity-invitations`
- `GET /v1/platform/identity-invitations/{invitation_id}`
- `POST /v1/platform/identity-invitations/{invitation_id}/resend`
- `POST /v1/platform/identity-invitations/{invitation_id}/cancel`

Creation is idempotent within a service client by `(source_client_id, external_reference)`. A retry refreshes an unconsumed challenge instead of creating duplicate identities.

## Owner activation

- Browser: `GET/POST /account/activate`
- API: `POST /v1/identity-invitations/activate`

SMS activation uses a six-digit one-time code. Email activation uses a high-entropy one-time link token. Codes are stored using the password hashing function; link tokens are stored only as SHA-256 digests. Invitations expire after 24 hours and lock after repeated invalid activation attempts.

The business owner's phone number is never used as a password. Trade, RSL or another trusted caller never receives the owner's password, passkeys, MFA secrets or recovery codes.
