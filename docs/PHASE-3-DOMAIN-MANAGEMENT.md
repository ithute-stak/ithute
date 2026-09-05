# Phase 3 — Domain Management

Phase 3 turns domains into first-class, tenant-owned resources before authoritative DNS is delegated to PowerDNS in Phase 4.

## 120% acceptance criteria

- Globally unique normalized domain identities with IDN/punycode support.
- Tenant-isolated domain CRUD with granular `dns.read` / `dns.manage` RBAC.
- Safe lifecycle: pending verification, verified, suspended, archived.
- DNS TXT ownership verification with cryptographically random one-time challenges.
- Verification challenge regeneration and attempt history.
- Domain metadata: display name, notes, mail intent, DNS hosting intent, creation/verification timestamps.
- Search, status filtering and deterministic pagination.
- Duplicate-domain and cross-tenant ownership protection.
- Domain activity history and audit logging.
- Readiness payload for Phase 4 showing required nameservers and delegation state.
- Responsive domain administration UI with add-domain, verification instructions, status badges and archive controls.
- Alembic migration from Phase 2 without rewriting prior migrations.
- Integration tests for normalization, RBAC, tenant isolation, duplicate ownership, verification and lifecycle controls.
- Dedicated disposable Docker verification gate.

## Ownership verification

A domain is added in `pending_verification` state. The platform generates a challenge and asks the administrator to publish:

- Host: `_mailbox-dns-verification.<domain>`
- Type: `TXT`
- Value: `mailbox-dns-verification=<token>`

The backend resolves TXT records independently. A matching value marks the domain verified and records the verification timestamp. Regenerating a challenge invalidates the previous challenge.

## Phase 4 boundary

Phase 3 does not create authoritative DNS zones. It prepares the domain resource, ownership proof and delegation intent. Phase 4 connects these verified domains to PowerDNS, creates zones/records, checks NS delegation, enables DNSSEC and manages secondary DNS.
