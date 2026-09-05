# Phase 7 — Database-backed Mailbox Management

Phase 7 turns the working Postfix/Dovecot/Rspamd data plane into a tenant-managed mail product. PostgreSQL is now the source of truth for mailboxes, aliases and distribution groups; Postfix and Dovecot query it live, so mailbox lifecycle changes do not require rebuilding containers or regenerating static map files.

## Implemented foundation

- Mailbox schema with tenant/domain ownership, globally unique address, status, password hash, quota and audit metadata.
- Alias routes and distribution groups with tenant isolation.
- Strong mailbox password validation and Dovecot-compatible SHA512-CRYPT hashes.
- Mailbox API for create/list/get/update/password change/suspend/restore/archive.
- Alias API for create/list/delete.
- Distribution-group API for create/list/add member.
- Platform-owner, tenant-admin and mail-admin authorization through existing RBAC.
- PostgreSQL-backed Postfix virtual domains, mailbox recipients, aliases and distribution groups.
- PostgreSQL-backed Dovecot passdb/userdb.
- Existing Phase 6 smoke fixture migrated from committed flat files to database seeding.
- Functional Mailboxes control-panel page with organization context, mailbox create/list/suspend/restore/password reset, alias creation and group creation.
- Phase 7 backend tests and verification gate.

## Security boundaries

Platform account passwords and mailbox passwords are separate. Mailbox hashes are never exposed through API responses. Mailbox creation is allowed only on verified, mail-enabled domains. Alias destinations are restricted to active mailboxes or groups within the same tenant, preventing accidental unrestricted external forwarding.

Suspended and archived mailboxes are excluded from the Dovecot authentication query and active-recipient Postfix lookup. This means suspension is enforced by the mail data plane rather than only by the UI.

## Verification

Run:

```sh
sh scripts/verify-phase7.sh
```

The gate reruns Phase 6, applies migration `0004`, executes mailbox API tests and verifies that Postfix and Dovecot are using live PostgreSQL lookups rather than static passwd/hash maps.

Acceptance target:

```text
Phase 7 foundation verification PASSED.
```

## Remaining Phase 7 work

Before Phase 7 is considered fully complete, add enforced Dovecot storage quota accounting, per-mailbox actual usage reporting, group-member management in the UI, alias deletion UI, mailbox archive/retention UI, mail storage operational metrics, and a dedicated API-driven live integration smoke proving that a mailbox created through the control-plane API can authenticate immediately without any service restart.

Phase 8 remains responsible for public deliverability: DKIM, SPF, DMARC, production TLS, PTR/HELO readiness, outbound abuse controls, bounce handling and reputation monitoring.
