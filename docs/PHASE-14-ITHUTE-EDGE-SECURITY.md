# Phase 14 — !thute Edge & Security

## Purpose

Phase 14 starts the shared !thute edge platform that can eventually protect Mail & DNS, LoanHub, !thute Schools, POS, Construction, Collections and customer-hosted applications from one control plane.

The design intentionally separates **telemetry that is active today** from **policy that requires a distributed edge runtime**. A single VPS is not represented as a Cloudflare-scale global Anycast/CDN/DDoS network.

## Active in Phase 14.1

### Public origin health checks

- HTTP and HTTPS origins can be inspected on demand.
- Probes connect to a resolved public IP directly and preserve the requested hostname for HTTP Host and TLS SNI.
- Private, loopback, link-local, reserved and otherwise non-global targets are refused to prevent the feature becoming an SSRF path into !thute infrastructure.
- The result stores HTTP status, latency, selected IP and health state.

### TLS and certificate inspection

HTTPS inspections also store:

- negotiated TLS protocol;
- cipher;
- certificate issuer;
- certificate expiry;
- days remaining until expiry.

This creates the foundation for expiry alerts and an eventual certificate manager.

### DNS zone intelligence

For verified PowerDNS-managed domains the platform can read and snapshot:

- zone kind;
- SOA serial;
- DNSSEC state;
- RRset count;
- total record count;
- record distribution by DNS type.

This is zone/inventory analytics. Per-query volumes, countries, response codes and resolver analytics require authoritative-query telemetry and are not claimed by this phase.

## Control-plane policy introduced in Phase 14.1

Each verified hostname can be registered as an `EdgeApplication` with:

- DNS-only or protected policy mode;
- cache policy;
- WAF policy;
- bot-protection policy;
- API-shield policy;
- access/Zero Trust policy flag;
- request-per-minute limit;
- TLS mode and minimum TLS version;
- health path and expected response.

Applications can have multiple origins with weights and failover priorities. They can also have ordered rules for firewall, rate-limit, cache, redirect, header, access, API-shield and bot policy.

These settings are persisted now so subsequent edge nodes consume one stable policy model. **Saving a protected policy does not yet claim that public traffic is being intercepted or filtered.**

## Runtime roadmap

### Phase 14.2 — Protected reverse proxy

- dedicated !thute edge runtime;
- protected DNS/proxy activation workflow;
- origin routing;
- trusted forwarding headers;
- request and security event logging;
- automatic TLS for protected hostnames.

### Phase 14.3 — WAF, rate limiting and cache

- request rule evaluation;
- managed WAF rules;
- IP/path/host/header conditions;
- rate-limit counters;
- cache eligibility, TTL and bypass rules;
- security events and analytics.

### Phase 14.4 — Traffic manager

- continuous health scheduler;
- weighted load balancing;
- active/passive failover;
- origin draining;
- recovery and failback policy.

### Phase 14.5 — Tunnel and !thute Access

- outbound `ithute-agent` tunnel from private origins;
- relay authentication and key rotation;
- identity-gated application access;
- MFA/session/device policy integration;
- no public inbound port requirement for private services.

### Phase 14.6 — Regional edge network

- multiple independently operated edge locations;
- regional cache and proxy capacity;
- shared policy distribution;
- failover between edge locations;
- per-location telemetry.

Global CDN/Anycast/DDoS claims must only be made when real infrastructure supports them.

## Data model

- `edge_applications` — protected hostname and high-level policy.
- `edge_origins` — origin pool and health configuration.
- `edge_rules` — ordered security/traffic rules.
- `edge_inspections` — persisted health and TLS observations.
- `dns_zone_analytics_snapshots` — DNS inventory snapshots.

## API

Tenant-scoped endpoints are under:

`/api/v1/tenants/{tenant_id}/edge`

The capability endpoint exposes whether each feature is `active`, `control_plane`, or `planned`. This state is part of the product contract and prevents UI/marketing from describing configuration-only functionality as active enforcement.

## Security boundaries

1. Only verified domains can become edge applications.
2. Hostnames must remain inside their selected managed domain.
3. Health probes reject non-public destinations.
4. Health probes do not follow redirects.
5. Origin credentials embedded in URLs are rejected.
6. Rule changes require tenant DNS-management permission and are audit logged.
7. Inspection and DNS analytics reads require tenant DNS-read permission.
8. The future runtime must re-apply the same destination safety rules; stored configuration alone must never bypass them.
