# Phase 5 — DNS Security, Delegation & Automation

Phase 5 turns the authoritative DNS engine into an operational DNS platform. Phase 4 created and edited PowerDNS zones; Phase 5 adds DNSSEC lifecycle controls, delegation/propagation diagnostics, reusable DNS templates and verified primary/secondary transfer behavior.

## Implemented in the control plane

- DNSSEC status endpoint for each managed zone.
- DNSSEC enable flow through the PowerDNS HTTP API with API rectification enabled.
- DNSSEC key/DS extraction without exposing private key material.
- Safe DNSSEC disable guard: signing cannot be disabled while a parent DS is still visible.
- Delegation diagnostics comparing public NS answers with the platform nameserver pair.
- Nameserver A/AAAA resolution checks.
- Public SOA and parent DS diagnostics.
- Authoritative PowerDNS zone state included in diagnostics.
- DNS templates for website bootstrap, mail readiness and CAA security baseline.
- Tenant-RBAC protected template application with audit/domain events.
- PowerDNS errors carry structured HTTP status codes for reliable control-plane handling.
- Newly provisioned platform zones are PowerDNS `Master` zones with API rectification enabled so they can participate in primary/secondary replication.
- Base PowerDNS runs with primary support enabled.

## API

Base: `/api/v1/tenants/{tenant_id}/domains/{domain_id}/dns`

- `GET /dnssec`
- `POST /dnssec/enable`
- `POST /dnssec/disable`
- `GET /diagnostics`
- `GET /templates`
- `POST /templates/{template_name}`

## DNSSEC operating sequence

1. Provision the authoritative zone.
2. Enable DNSSEC in the control plane.
3. Copy one of the returned DS records to the registrar/parent zone.
4. Wait until diagnostics show the parent DS.
5. Keep signing enabled while the DS is published.

To disable DNSSEC safely, remove the parent DS first, wait for it to disappear publicly, then disable signing in the platform.

## Secondary DNS verification topology

`docker-compose.phase5-secondary.yml` adds an isolated second PowerDNS instance with its own PostgreSQL database and a dedicated test network. The primary and secondary therefore do not share the PowerDNS database. This is intentional: the Phase 5 integration gate proves actual DNS zone transfer behavior instead of accidentally succeeding through shared storage.

The test topology uses a fixed private subnet only for local verification. The primary permits AXFR only from the known test-secondary address. The secondary runs with secondary support enabled and retrieves a `Slave` zone from the primary through AXFR.

`scripts/phase5-secondary-smoke.py` verifies all of the following against real PowerDNS processes:

- creation of a primary/Master test zone;
- authoritative A-record answers from the primary;
- DNSSEC enablement;
- DS generation;
- DNSKEY publication;
- creation of an independent secondary/Slave zone;
- AXFR from primary to secondary;
- authoritative answers from the secondary;
- a second transfer after the primary record changes;
- matching SOA data after synchronization;
- cleanup of the temporary test zone.

This topology is an integration test, not a substitute for geographic redundancy. Production still requires `ns1` and `ns2` on independent public hosts/failure domains.

## Acceptance gate

Run:

```sh
sh scripts/verify-phase5.sh
```

The verifier now rebuilds the backend and frontend before testing, starts the independent secondary topology, runs migrations and the complete backend suite, executes the DNSSEC + AXFR integration smoke test, rebuilds the frontend, and performs route checks.

The local acceptance result must end with:

```text
Phase 5 verification PASSED.
```

A successful local gate proves software-level DNSSEC signing and secondary transfer behavior. Public production acceptance additionally requires a real delegated test/customer domain, parent DS publication, and two publicly reachable nameservers on separate hosts.
