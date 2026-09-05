# Commercial Releases B and C

## Release B — Professional Email

Release B completes the managed-email feature set around the existing Postfix/Dovecot/Rspamd data plane.

- Generic IMAP, Google Workspace/Gmail, Microsoft 365/Office 365 and cPanel migration paths.
- Bulk migration orchestration with per-mailbox progress and failure records.
- Shared mailbox access through Dovecot ACL delegation.
- Vacation responders and custom Sieve rules stored in PostgreSQL and synchronized to the mailbox filesystem.
- Per-mailbox encrypted-backup recovery through a private token-protected recovery service.
- PTR, forward-confirmed reverse DNS and DNSBL reputation snapshots.
- Email-verification and protected public signup.

Source migration passwords/app-passwords/OAuth tokens are accepted only for the migration execution request and are not persisted in the migration job table.

## Release C — Hosting Company

- Reseller accounts and reseller/customer tenant hierarchy.
- White-label brand configuration.
- OpenSRS XCP registrar adapter for lookup and registration. The adapter is disabled until reseller credentials are supplied.
- CalDAV/CardDAV groupware using Radicale with mailbox-specific bcrypt credentials.
- SMTP-only application credentials that cannot authenticate to IMAP.
- Transactional email API using tenant-scoped API keys with `mail.send` scope.
- Per-credential and per-tenant daily sending limits.
- Mail-node registry/heartbeat endpoints.
- Optional HAProxy TCP mail edge for SMTP, submission and IMAPS.
- Optional Dovecot dsync replication configuration for multi-node mailbox storage.

## Billing and entitlement hardening

Mailbox creation, quota growth and API-key creation now use the same subscription entitlement service already used by domain provisioning. API keys are tenant-scoped. DPO Pay hosted checkout is implemented behind credential-gated configuration; manual/EFT invoicing remains available when DPO is not configured.

## Production boundaries

The code contains real provider adapters, but external accounts are operator prerequisites. DPO merchant credentials and OpenSRS reseller credentials are not bundled or fabricated. Production also requires public TLS, clean mail IP/PTR, an independent secondary nameserver, off-site Restic storage, and firewalling of private replication/operations ports.
