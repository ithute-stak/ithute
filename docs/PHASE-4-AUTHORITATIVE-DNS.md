# Phase 4 — PowerDNS Authoritative DNS

Phase 4 attaches the custom multi-tenant control plane to PowerDNS Authoritative. The application remains the authorization and audit boundary; PowerDNS is the public DNS data plane.

## Implemented

- PowerDNS Authoritative service with PostgreSQL gpgsql backend.
- PowerDNS HTTP API is private to the Docker network; only DNS TCP/UDP 53 is published.
- Dedicated PowerDNS database and persistent volume, separate from the application database.
- Backend PowerDNS API client with timeout and error isolation.
- Verified, platform-DNS domains can provision/reconcile an authoritative Native zone.
- Tenant RBAC is enforced before every zone or record operation.
- Supported tenant record sets: A, AAAA, CNAME, MX, TXT, CAA and SRV.
- Record names are constrained to the managed zone; A/AAAA values are address-validated and apex/multi-value CNAME is rejected.
- TTL bounds and record-set size bounds are enforced.
- Zone and RRset mutations write domain events and application audit logs.
- PowerDNS API key is configuration-only and never returned through the tenant API.
- Production configuration rejects placeholder PowerDNS secrets and placeholder authoritative NS names.
- The control-plane UI now includes a guided DNS editor, safe-delete confirmation, conflict hints, JSON/CSV export, import preview, onboarding, audit, status and help surfaces.

## API

Base: `/api/v1/tenants/{tenant_id}/domains/{domain_id}/dns`

- `GET /health` — verify the PowerDNS control-plane connection.
- `POST /zone` — idempotently provision/reconcile a zone after ownership verification.
- `GET /zone` — inspect the authoritative zone and RRsets.
- `PUT /records` — replace an RRset.
- `DELETE /records?name=...&type=...` — delete an RRset.

## Security boundary

A domain must be ownership-verified, in `verified` state, and use `dns_mode=platform` before PowerDNS operations are permitted. The PowerDNS web/API port is intentionally not mapped to the host. The application talks to it over the private Docker network with `X-API-Key`.

## Production topology

One PowerDNS container is sufficient for local integration testing, but production authority must use at least two independently reachable authoritative nameservers on separate hosts/failure domains. Phase 5 adds secondary-DNS automation, DNSSEC, propagation/delegation diagnostics and templates.

## Acceptance

Before declaring Phase 4 complete, verify Compose, start PowerDNS and its database, confirm `pdns_control rping`, run the backend suite, build the frontend/production images, provision a test zone through the authenticated application API, create records, query the zone over both UDP and TCP, restart PowerDNS, prove the records remain authoritative, and run the dedicated Phase 4 verification gate when present.
