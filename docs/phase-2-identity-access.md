# Phase 2 — Identity & Multi-Tenancy

Phase 2 changes Mailbox-DNS from tenant-owned users to a global identity model suitable for a real multi-tenant SaaS control plane.

## Identity model

- `users` is the global person/login identity. Email is globally unique and normalized to lowercase.
- `tenant_memberships` links one user to one or more companies.
- Platform ownership is a global privilege on the user, separate from company roles.
- Company membership status can be active or suspended without disabling the global user.
- Built-in company roles are `tenant_admin`, `dns_admin`, `mail_admin`, `auditor`, and `member`.
- Permission mapping is centralized in `app/core/rbac.py` so later DNS and mail APIs can reuse the same authorization layer.

## Authentication security

- Short-lived JWT access tokens remain supported for API compatibility.
- Browser authentication uses HttpOnly access and refresh cookies instead of `localStorage`.
- Refresh tokens are random, stored only as SHA-256 hashes, and rotated on every refresh.
- Sessions capture user agent, source IP, expiry and revocation state.
- Session versioning invalidates old access tokens after security-sensitive changes.
- Password changes, MFA enable/disable and revoke-all invalidate refresh sessions.
- TOTP MFA secrets are encrypted at rest using a Fernet key derived from the platform secret key.
- Production configuration requires secure cookies.

## Company identity administration

Tenant admins and platform owners can:

- list company members;
- invite a new or existing global identity;
- select granular roles;
- cancel pending invitations;
- change membership roles;
- suspend/reactivate memberships;
- view their own company memberships.

The API prevents removal or suspension of the last active tenant administrator.

## API keys

Authenticated users can create scoped API keys. Only a hash is persisted. The clear key is returned only at creation time. Keys support expiration and revocation. Later DNS and mail APIs will consume these scopes.

## Audit events

Phase 2 emits audit events for login, refresh, logout, session revocation, MFA changes, password changes, invitation lifecycle, membership changes and API-key lifecycle.

## UI

- `/login` uses cookie authentication and supports MFA challenge.
- `/dashboard` reflects Phase 2 identity capabilities.
- `/organizations` shows all companies attached to the global identity.
- `/tenants/[tenantId]/members` manages members, roles and invitations.
- `/security` manages TOTP setup and active sessions.

## Verification

Run:

```bash
sh scripts/verify-phase2.sh
```

The Phase 2 gate validates Compose, rebuilds the current backend image, exercises Alembic upgrade/downgrade/upgrade, runs the full backend suite, builds the frontend, and builds production images.

## Open-source infrastructure integration timeline

Phase 2 deliberately remains control-plane focused. Infrastructure engines are introduced after identity and domain ownership are stable:

1. Phase 3 — custom domain onboarding/verification data model.
2. Phase 4 — PowerDNS Authoritative integration, public zones, nameserver delegation and DNS automation.
3. Phase 5 — DNSSEC, propagation, templates, ACME/automation foundations.
4. Phase 6 — Postfix + Dovecot mail data plane and mailbox provisioning; Rspamd service wiring begins here.
5. Phase 8 — full SPF/DKIM/DMARC, Rspamd policy/tuning, deliverability controls and reputation workflows.
6. Later production hardening — public TLS/ACME automation, monitoring, backups and multi-node redundancy are finalized before launch.
