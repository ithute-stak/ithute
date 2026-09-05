# Mailbox DNS

Mailbox DNS is a production-oriented, multi-tenant **business email + authoritative DNS + hosting-company platform** built by Lelefa Infrastructure.

The original technical roadmap is complete at Phase 13/13. Commercial Release A (Business Launch), Release B (Professional Email) and Release C (Hosting Company) are represented in the control plane and production stack.

## Current product surface

- Multi-tenant organizations, memberships, RBAC, MFA, sessions and tenant-scoped API keys
- Protected public signup, email verification, rate limiting and optional Cloudflare Turnstile
- Domain ownership verification and lifecycle
- PowerDNS authoritative zones, DNSSEC, delegation diagnostics and record automation
- Postfix + Dovecot + Rspamd + Unbound mail data plane
- Database-backed mailboxes, quotas, aliases and distribution groups
- Shared/delegated mailboxes, vacation responders and Sieve filtering
- Google Workspace/Gmail, Microsoft 365, cPanel and generic IMAP mailbox migration
- Per-mailbox encrypted-backup recovery and deliverability/reputation snapshots
- Webmail with folders, search, drafts, attachments, HTML sanitization, contacts and signatures
- SPF/DKIM/DMARC readiness, DKIM lifecycle, sender ownership and queue operations
- SMTP-only application credentials and tenant API transactional email
- CalDAV/CardDAV groupware using Radicale
- Reseller accounts, reseller/customer hierarchy and white-label brand settings
- OpenSRS domain lookup/registration adapter, credential-gated until reseller credentials are supplied
- DPO Pay hosted checkout adapter plus manual/EFT invoicing, credential-gated until merchant credentials are supplied
- Starter/Business/Enterprise entitlement enforcement for domains, mailboxes, allocated storage and API keys
- Encrypted Restic backups, restore drills and private mailbox recovery service
- Prometheus, Grafana, Alertmanager and synthetic SMTP/IMAP/DNS monitoring
- Mail-node registry, optional Dovecot dsync replication and optional HAProxy TCP mail edge
- Customer billing portal, notifications, support centre and public service status
- Caddy HTTPS production edge and production preflight validation

## Development

```bash
cp .env.example .env
docker compose up -d --build
```

Default endpoints: frontend `http://localhost:3006`, backend `http://localhost:8006`, API docs `http://localhost:8006/docs`, SMTP `localhost:2525`, submission `localhost:2587`, IMAPS `localhost:2993`.

Add the mail overlay for SMTP/IMAP/Rspamd/Radicale services:

```bash
docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml up -d --build
```

## Commercial regression

```bash
sh scripts/verify-commercial-release.sh
```

The gate runs the historical Phase 1–13 regression chain, Commercial A/B/C API tests, current Alembic head validation, production frontend build, unified production Compose, optional HA mail Compose and Caddy configuration validation. GitHub Actions runs the same gate on `development`, `main`, pull requests to `main`, and manual dispatch.

## Production

Read `docs/COMMERCIAL-RELEASE.md`, `docs/COMMERCIAL-RELEASES-BC.md` and `docs/PRODUCTION-TOPOLOGY.md`, create a secure production `.env`, then run:

```bash
sh scripts/prod-preflight.sh
sh scripts/prod-up.sh
```

The normal primary stack includes the customer/control plane, mail data plane, primary authoritative DNS, encrypted backup scheduler, groupware, monitoring and ACME HTTPS edge. `HA_MAIL_ENABLED=true` adds the HAProxy TCP mail edge and requires independently addressable mail nodes.

**Production NS2 must run on an independent public server/failure domain.** Off-site Restic storage must also be a separate failure domain. DPO merchant credentials, OpenSRS reseller credentials, public TLS/PTR configuration and external accounts are operator prerequisites and are intentionally not fabricated in source control.

Before moving real customer MX or nameserver delegation: use real public hostnames/IPs, configure PTR/rDNS, use public mail TLS certificates, verify port 25/587/993/53 access, externally validate SPF/DKIM/DMARC, isolate replication/operations ports, run the commercial regression and complete a real external delivery/restore test.

Repository production policy is documented in `docs/PRODUCTION-READINESS.md` and vulnerability handling in `SECURITY.md`. Frontend dependencies are locked with `package-lock.json`; production images use `npm ci`; Dependabot targets `development`; and GitHub Actions dependencies are pinned to immutable commit SHAs.
# ithute
# ithute
