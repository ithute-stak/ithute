# Phase 2 — Identity & Multi-Tenancy (120% target)

Phase 2 turns the Phase 1 foundation into a production-grade identity and access control plane for a multi-tenant email and DNS SaaS.

## Architecture decision

Users are global identities. A user does not belong to exactly one company. Company access is represented by a tenant membership, so one identity can safely belong to multiple companies while mailboxes remain a separate future resource.

## Required deliverables

- Global user identity with normalized unique email addresses.
- Tenant membership table with tenant-admin and member roles.
- Platform-owner role separated from tenant roles.
- Tenant member management and role/status changes.
- Tenant invitation lifecycle: create, expire, revoke, accept, audit.
- Secure browser sessions using HttpOnly/Secure/SameSite cookies.
- Short-lived access tokens plus rotating refresh tokens.
- Server-side session registry and revocation.
- Logout, session listing, individual session revocation, revoke-all support.
- MFA/TOTP enrollment, verification, enable/disable and login challenge.
- Encrypted MFA secrets at rest.
- API keys stored only as hashes; plaintext shown once.
- API-key revocation, expiry and scopes foundation.
- Granular RBAC dependencies for platform and tenant operations.
- Expanded audit events with metadata and source IP.
- Case-normalized identity lookup to remove Phase 1 email ambiguity.
- Migration from the Phase 1 user/tenant-role model without losing existing users.
- Integration tests covering authentication, cookies, refresh rotation, revocation, MFA, invitations, tenant isolation, RBAC and API keys.
- Phase 2 verification must run through the existing disposable PostgreSQL/Redis Docker test gate before merge.

## Security acceptance criteria

Phase 2 is not complete until:

1. Browser login no longer requires storing an access token in localStorage.
2. A revoked session cannot use either access or refresh credentials.
3. MFA-enabled accounts cannot authenticate without a valid second factor.
4. Tenant members cannot perform tenant-admin actions.
5. A user can belong to multiple tenants without duplicated identities.
6. Invitation tokens, refresh tokens and API keys are never stored in plaintext.
7. Existing Phase 1 users migrate cleanly into the new identity/membership model.
8. All Phase 1 tests remain green and the expanded Phase 2 test suite is green.

## Open-source infrastructure integration boundary

Phase 2 remains control-plane identity work. PowerDNS integration begins in Phase 4 after domain management in Phase 3. Postfix and Dovecot integration begins in Phase 6. Rspamd is introduced with the mail data plane in Phase 6 and is fully wired into authentication/deliverability policy during Phase 8. This ordering prevents mail and DNS engines from being coupled to an unstable identity model.
