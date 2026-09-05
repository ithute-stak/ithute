# Ithute Operating Platform

## Purpose

Mailbox-DNS is the control-plane repository for the Ithute application ecosystem. Each product owns its business database and business rules. Shared platform services provide identity, push delivery, realtime transport, product registry, operating telemetry, licensing, notifications, security metadata, deployment commands and event routing.

## Non-negotiable data boundary

- LoanHub business data stays in the LoanHub PostgreSQL database.
- Ithute Pay business data stays in the Ithute Pay PostgreSQL database.
- Ithute Tutor business data stays in the Ithute Tutor PostgreSQL database.
- Mailbox business data stays in the Mailbox PostgreSQL/mail storage stack.
- The control plane stores only registry, health, deployment, backup, event, licensing, notification and security metadata.
- No control-center API is allowed to query a product database directly.

## Platform services

Central Auth owns identity, MFA/passkeys, sessions and short-lived service-token issuance. Central Push owns provider delivery. Central Realtime owns websocket transport. Products keep product authorization and business state.

### Product Registry

Every product has a `product.manifest.yaml` declaring its identity, central-service dependencies, database ownership and deployment boundary. Initial registry members are `mailbox-dns`, `loanhub`, `ithute-pay` and `ithute-tutor`.

### Event Bus contract

Products obtain central Auth service tokens with audience `ithute-platform`. The control plane checks signature, token type, authorized client and required scope before accepting an event. Events are idempotent by `product_id + source_event_id`.

Recommended event names include:

- LoanHub: `loan.approved`, `loan.payment_received`, `loan.overdue`, `borrower.updated`
- Pay: `payment.received`, `payment.failed`, `wallet.credited`, `transfer.completed`
- Tutor: `lesson.scheduled`, `assignment.created`, `result.published`, `student.enrolled`
- Mailbox: `mail.received`, `mail.delivery_failed`, `mailbox.quota_warning`, `domain.expiring`, `dns.verification_failed`

The current release establishes the durable event/notification contract and product-authenticated ingestion API. Push/Realtime consumers can subscribe to this contract without moving business logic into the platform.

### Product heartbeats and commands

Products can report version, operational status, database health, Auth/Push/Realtime connectivity, container summary, metrics and last error. The Superadmin can queue maintenance, backup, restore, healthcheck, migrate, deploy and rollback commands. Product-side agents must authenticate with central Auth before polling or updating commands.

## Unified licensing and App Launcher

`ithute_subscription_grants` controls commercial access for a user, organization or tenant with `demo`, `active`, `suspended` and `expired` states. Product RBAC stays product-owned. `/ithute-account` exposes the applications available to the current identity and a persistent notification inbox; central password/MFA/passkey management remains at central Auth.

## Secrets and observability

The platform stores secret references and rotation metadata, never raw secret values. Heartbeats and event trace IDs establish the telemetry contract; service calls should propagate request IDs and W3C trace context. An OTLP collector/exporter can be added without changing product business databases.

## Mail intelligence

Mailbox includes tenant-scoped models/APIs for retention policies, legal hold flags, immutable archive policy metadata, DMARC aggregate analytics, phishing findings and mail automation rules. They use existing `mail.read`/`mail.manage` permissions.

## LoanHub production protection

LoanHub deployment must preserve the existing Compose project identity and PostgreSQL volume. The production workflow aborts if the expected volume is absent or mounted incorrectly, creates a non-empty `pg_dump` before Alembic, and never removes Docker volumes. See `docs/VPS-PLATFORM-RUNTIME.md`.

## Governance

`main` is the release branch. The repository includes the `Ithute Operating Platform` validation workflow, but GitHub branch protection/rulesets are account-level settings and must be enabled by a repository administrator. The intended ruleset requires pull requests, required regression checks, conversation resolution, and blocks force-push/branch deletion.

## Validation

Run:

```bash
sh scripts/validate-ithute-operating-platform.sh
```

This checks Python syntax, product manifest boundaries and the LoanHub production data-safety contract without requiring a hosted CI runner.
