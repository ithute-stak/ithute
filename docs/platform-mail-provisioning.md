# Ithute Platform Mail Provisioning API

This API is the machine boundary between standalone Ithute products and the mail runtime. Products do not edit Docker Mailserver account files, mount `/tmp/docker-mailserver`, receive Postfix/Dovecot credentials, or read the mail database directly.

## Trust model

A caller first obtains a short-lived RS256 service token from Ithute Auth. Mail accepts only tokens with:

- issuer `https://auth.ithute.co.ls` (or the configured Ithute Auth issuer);
- audience `ithute-mail`;
- `token_use=service`;
- a consistent `sub=service:<client_id>` and `azp=<client_id>` identity; and
- the exact required scope.

`mailbox.create` provisions and reads the caller's own provisioned mailbox. `mailbox.manage` suspends or reactivates one. The Business Digital Address client receives `mailbox.manage`; the Trade simulator intentionally does not.

## Domain bindings

A valid service token alone is not enough to create an address on an arbitrary Ithute-hosted domain. A platform owner must bind a service client to a verified, mail-enabled domain through:

`POST /api/v1/platform/mail/domain-bindings`

The binding independently controls creation and lifecycle management. This is intended to bind `business-digital-address` to the future approved official-business domain after that domain is registered and verified.

## Provisioning

`POST /api/v1/platform/mail/mailboxes`

Example body:

```json
{
  "external_reference": "BUS-LS-000001234",
  "domain": "rsl-business.ls",
  "local_part": "tjekatjeka",
  "display_name": "Tjekatjeka Holdings (Pty) Ltd",
  "quota_bytes": 1073741824
}
```

The pair `(service_client_id, external_reference)` is idempotent. Repeating the same request returns the same mailbox. Reusing the reference for a different address fails.

Ithute generates the underlying mailbox credential internally and stores only its Docker Mailserver-compatible hash. The credential is never returned to Trade, RSL, or Business Digital Address. The business owner will authenticate to the official-inbox application through central Ithute Auth.

The existing mailbox runtime synchronization listener remains the only bridge from application mailbox rows to Docker Mailserver's account file. Suspending a mailbox removes it from the active runtime account file; reactivation restores it.

## Lifecycle

- `GET /api/v1/platform/mail/mailboxes/{external_reference}`
- `POST /api/v1/platform/mail/mailboxes/{external_reference}/suspend`
- `POST /api/v1/platform/mail/mailboxes/{external_reference}/activate`

A caller can see/manage only provisioning rows created under its own service identity.

## Deliberately not included yet

External forwarding/notification delivery is not implemented as a Docker Mailserver alias in this step. The official mailbox must remain the source of record, while delivery to `info@company.co.ls` will be implemented as a separate authenticated delivery-copy service with retries and delivery receipts. That avoids accidentally turning ordinary aliases into the legal/official archive mechanism.
