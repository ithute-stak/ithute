# Phase 13 — SaaS & Billing

Phase 13 introduces the commercial control plane without coupling Mailbox-DNS to a specific payment processor.

## Foundation

The accepted foundation provides:

- A persistent billing plan catalog in LSL.
- Tenant subscriptions with trialing, active, past-due, and canceled states.
- Tenant usage snapshots for mailbox count, domain count, allocated mailbox storage, and API-key usage.
- Invoice persistence.
- Plan entitlements for mailboxes, domains, allocated storage, and API keys.
- Tenant-admin billing read/manage permissions and auditor read access.
- Platform-owner subscription assignment.
- Bootstrap seeding of Starter, Business, and Enterprise plans.
- Audit events for subscription assignment and usage snapshots.

## Billing operations increment

The second Phase 13 increment adds production-oriented billing lifecycle primitives without storing card or bank credentials:

- Billing-period usage snapshots linked to invoices.
- Idempotent invoice generation for each subscription billing period.
- Open invoices with explicit due dates, period boundaries, currency, subtotal, and total in integer minor units.
- Provider-neutral payment-event persistence with a unique `(provider, event_id)` idempotency key and SHA-256 payload hash.
- HMAC-SHA256 authenticated webhook ingestion through `POST /api/v1/billing/webhooks/{provider}` using `X-Billing-Signature`.
- Payment-success, payment-failure/past-due, subscription-active, and subscription-canceled lifecycle processing.
- Configurable payment grace period through `BILLING_GRACE_DAYS`.
- Non-destructive entitlement decisions: canceled subscriptions and past-due subscriptions after grace cannot create new paid resources; existing domains/mailboxes are not deleted.
- Domain creation enforcement now checks the tenant's billing entitlement before accepting a new domain.
- Read-only entitlement diagnostics are available under `/api/v1/tenants/{tenant_id}/billing/entitlements/{resource}`.
- Invoice listing and platform-owner invoice generation APIs.

## Pricing boundary

Default prices are catalog data expressed in minor LSL units and are not a legal quotation. They can be changed before production launch. The platform does not store card data, debit bank accounts, or claim integration with any specific Lesotho payment provider.

Invoice totals currently charge the plan's base monthly price. Usage is metered and attached to the invoice period, but overage charging is intentionally not invented because the catalog does not yet define per-mailbox, per-domain, or per-GB overage prices.

## Usage semantics

`storage_bytes` currently records allocated mailbox quota, not physical Maildir bytes consumed. Billing-period snapshots record `period_start` and `period_end` so a later physical-storage collector can replace or supplement allocated quota without changing the invoice lifecycle.

## Payment-provider boundary

Subscriptions default to provider `manual`. The public billing webhook is provider-neutral. A real provider adapter must validate the provider's native signature at the trusted edge and map the verified event into the canonical Mailbox-DNS event format. The backend additionally authenticates the canonical body with `BILLING_WEBHOOK_SECRET`.

Canonical event bodies contain `event_id`, `event_type`, and the relevant `tenant_id` and/or `invoice_id`. Supported lifecycle event types are:

- `invoice.paid`
- `invoice.payment_failed`
- `invoice.past_due`
- `subscription.active`
- `subscription.canceled`

Production requires a dedicated `BILLING_WEBHOOK_SECRET` of at least 32 characters, distinct from `SECRET_KEY` and `DKIM_ENCRYPTION_KEY`. Provider credentials and webhook secrets must never be committed to source control.

## Dunning and entitlement policy

A failed payment moves the subscription to `past_due`, records `past_due_since`, and creates `grace_ends_at`. During grace, existing service continues and new resources are still permitted if they fit the plan. After grace expires, creation of additional paid resources is denied. Payment success returns the subscription to `active` and clears dunning timestamps.

The policy is deliberately non-destructive. Billing state does not automatically archive domains, delete mailboxes, erase mail, or remove DNS zones. More aggressive suspension, if ever required, must be a separately reviewed production policy.

## API surface

- `GET /api/v1/billing/plans`
- `GET /api/v1/tenants/{tenant_id}/billing/summary`
- `GET /api/v1/tenants/{tenant_id}/billing/entitlements/{resource}`
- `POST /api/v1/tenants/{tenant_id}/billing/usage/snapshot`
- `PUT /api/v1/tenants/{tenant_id}/billing/subscription`
- `GET /api/v1/tenants/{tenant_id}/billing/invoices`
- `POST /api/v1/tenants/{tenant_id}/billing/invoices`
- `POST /api/v1/billing/webhooks/{provider}`

## Remaining Phase 13 work

Before final Phase 13 acceptance, mailbox/storage and tenant-scoped API-key creation must use the same entitlement gate, provider adapters can be added when a payment provider is selected, the billing UI must expose plans/subscription/invoices/dunning state, and the final verifier must exercise signed webhook replay/idempotency and grace-period enforcement end to end.
