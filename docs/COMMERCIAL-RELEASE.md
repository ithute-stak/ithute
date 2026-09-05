# Mailbox DNS Commercial Release

Mailbox DNS is now structured as a customer-facing email and DNS hosting business, not only an infrastructure control plane.

## Customer lifecycle

1. Visitor reviews `/pricing`.
2. Customer creates a company at `/signup` and receives a 14-day trial on Starter, Business or Enterprise.
3. The tenant administrator signs in, completes onboarding, verifies a domain and provisions DNS/mailboxes.
4. Billing usage and invoices are visible at `/billing`.
5. Operational and account notices appear at `/notifications`.
6. Customers open mail, DNS, billing, migration or security requests at `/support`.
7. Public incidents are published at `/service-status`.

## Platform-owner operations

`/business-operations` exposes commercial KPIs including customer organizations, active users, mailboxes, domains, active/trial subscriptions, MRR, open invoices and support backlog. Platform owners can work the global support queue and publish service incidents.

## Payments

The billing core remains provider-neutral. Signed/idempotent webhooks can activate or place subscriptions into dunning states. Manual invoicing and platform-owner payment settlement allow the service to operate commercially before a specific Lesotho payment gateway is selected. A provider adapter can later translate a gateway's webhook into the existing trusted billing webhook contract.

## Legal baseline

`/legal` contains baseline Terms, Acceptable Use, Privacy, SLA and Retention policies. These are product defaults and must be reviewed by Lesotho legal counsel before external contracts are signed.

## Production boundary

The production control plane, primary authoritative DNS, mail data plane, encrypted backups and monitoring can be launched from one primary host using `scripts/prod-up.sh`. Authoritative secondary DNS must run on another public server/failure domain. Mail reputation is also best protected by using a dedicated mail IP/VPS when the service grows.
