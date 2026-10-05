# Ithute

Ithute is a **commercial hosting, communications and infrastructure control platform** operated as a standalone Ithute deployment.

It combines customer-facing hosting and business services with the control-plane capabilities needed to provision, secure, monitor, meter and commercialize infrastructure. The current repository includes web hosting, application hosting, business email/webmail, authoritative DNS, domains, billing and finance, quotations, infrastructure-node management, backups, observability, centralized identity, Push, Realtime, multi-language specialist engines and production automation.

Ithute is intentionally isolated from LoanHub, NBros/BuildTrack, Tutor, Pay and other products. It does not share their application databases, Docker networks, volumes or deployment directories. Other products may integrate through approved HTTPS/WSS contracts, but they do not become part of the Ithute runtime.

## Product direction

The long-term product is broader than a conventional shared-hosting panel.

Ithute is being built as a **hosting operating system and commercial infrastructure platform** for:

- direct hosting customers;
- professional-email customers;
- developers and software companies;
- businesses that need managed application hosting;
- hosting resellers and IT service providers;
- white-label partners;
- operators managing multiple VPS and dedicated-server nodes.

The core business idea is to connect infrastructure to Ithute, convert raw infrastructure into safely sellable capacity, provision managed services from that capacity, and connect every allocation to billing, margin, monitoring and operational control.

## Current platform capabilities

The main FastAPI control plane already exposes application areas for:

### Hosting and infrastructure

- infrastructure-server inventory;
- shared hosting;
- application hosting;
- hosting catalogues and plans;
- project provisioning and lifecycle operations;
- source credentials;
- Git webhook deployment;
- ZIP/source uploads;
- build settings, builds and build logs;
- database backup operations;
- metering;
- public hosting;
- edge routing;
- managed networking;
- hosting-node health and automatic placement controls.

The production configuration includes private hosting-network support using configurable WireGuard ranges, health reconciliation, auto-activation, auto-draining, recovery and delayed failover policy for eligible stateless workloads.

### Mail and webmail

Ithute includes a substantial mail platform rather than only mailbox provisioning:

- professional email;
- mailbox creation and routing;
- mail-node provisioning and operations;
- external mailbox connections;
- rich-message composition;
- attachments;
- drafts;
- forwarding;
- mailbox events;
- migration tools;
- mail intelligence;
- deliverability controls;
- transactional email;
- known-correspondent and preference handling;
- webmail productivity features;
- realtime mailbox-change events.

Mail state is isolated in the independent `ithute-mail` deployment and host storage.

### DNS and domains

The control plane includes:

- authoritative DNS;
- domain onboarding;
- domain orders;
- domain and mail-health checks;
- DNS lifecycle operations;
- customer edge routes.

Ithute is authoritative for the `ithute.co.ls` zone in the current production topology.

### Billing, finance and commercial operations

The repository includes:

- canonical pricing;
- plan administration;
- billing;
- payments;
- commercial operations;
- profitability analysis;
- corporate quotations;
- finance documents;
- finance operations;
- accounting;
- finance controls;
- governance;
- finance reporting;
- customer applications.

This allows infrastructure and service provisioning to be connected to commercial records instead of operating as an isolated technical panel.

### Security and governance

The application includes:

- audit trails;
- security-operation workflows;
- security approvals and dual control;
- tenant controls;
- delegated identity;
- system-owner telemetry;
- request hardening;
- rate controls;
- production safety checks;
- backup/restore assurance.

Destructive or high-risk operational actions should remain explicit, auditable and role-scoped.

## Architecture

The production application is organized around a Python control plane and separate Ithute-owned platform services.

```text
                         Internet
                            |
                          Caddy
                            |
          +-----------------+------------------+
          |                 |                  |
       Ithute Web       Ithute API        Platform services
       Next.js          FastAPI           Auth / Push / Realtime
                            |
       +--------------------+-------------------------+
       |          |          |          |             |
     Hosting     Mail       DNS      Finance       Billing
       |          |          |          |             |
       +----------+----------+----------+-------------+
                            |
                    specialist engines
                 Rust / Go / C++ / Java
```

### Frontend

`apps/frontend` is a Next.js/React application using TypeScript and Tailwind CSS.

Current core versions include:

- Next.js 15;
- React 19;
- TypeScript;
- Tailwind CSS 4.

The frontend is built into an immutable production image and served behind Caddy.

### Main control plane

`apps/backend` is the authoritative business/control plane.

Core technologies include:

- Python 3.12;
- FastAPI;
- SQLAlchemy;
- PostgreSQL;
- Redis;
- Alembic;
- Pydantic;
- Prometheus metrics;
- cryptographic and authentication libraries.

Python remains authoritative for tenancy, authorization, billing, orchestration and business decisions.

### Specialist multi-engine architecture

Ithute deliberately uses five backend languages where each has a bounded role:

| Engine | Primary role |
| --- | --- |
| Python / FastAPI | control plane, authorization, tenancy, billing, orchestration and business rules |
| Rust | memory-safe CPU-heavy parsing, MIME pre-scans, hashing and bounded transformations |
| Go | concurrent/network-oriented workers and probes |
| C++ | narrow benchmark-proven native hot paths |
| Java | enterprise XML, reporting and standards-heavy integration workloads |

The rule is simple:

> Python decides **what may happen**. Specialist engines execute bounded **how work**.

Specialist engines do not independently authorize tenant actions or reimplement billing/permission policy. Routed operations retain safe fallback behavior where appropriate.

The app API image currently compiles and embeds the Rust and C++ native libraries. Go is an independently deployable worker path, while Java is deployed as a hardened internal worker.

## Ithute-owned platform services

The `platform/` directory contains reusable services owned by Ithute.

### !thute Auth

Public origin:

```text
https://auth.ithute.co.ls
```

Auth provides centralized identity and SSO, including:

- RS256 access and ID tokens;
- JWKS;
- Authorization Code + PKCE;
- refresh-token rotation;
- centrally revocable sessions;
- TOTP MFA;
- recovery codes;
- account recovery;
- email/phone verification adapters;
- WebAuthn/passkeys;
- account lockout and failed-login throttling;
- security audit events;
- signing-key rollover;
- platform-admin and account portals.

Product business data remains outside Auth. Products link local profiles to the immutable Auth `sub`.

### !thute Push

Public origin:

```text
https://push.ithute.co.ls
```

Push owns device endpoints, queued notification delivery, retries and delivery-state handling.

Firebase Cloud Messaging may be used as an Android **last-mile transport**, but Firebase does not own Ithute identity, product data, business rules or notification history. Push can start without a mandatory provider and external providers remain adapters behind the Ithute service.

### !thute Realtime

Public origin:

```text
https://realtime.ithute.co.ls
wss://realtime.ithute.co.ls/v1/ws
```

Realtime provides:

- authenticated WebSockets;
- conversations;
- messages;
- memberships;
- read state;
- typing events;
- presence;
- Redis-backed fan-out;
- PostgreSQL-backed history;
- Push fallback for offline recipients.

Each product is isolated by authenticated application namespace.

### Ithute Notification

`platform/ithute-notification` exists as a multi-channel notification gateway for Push/email/SMS coordination, but it is **intentionally deferred as a required production dependency** until its activation checklist is complete.

Auth, Mail, DNS, Web, Push and Realtime must not depend on an unfinished Notification rollout.

## Repository map

```text
.
├── apps/
│   ├── frontend/              Next.js customer/admin web application
│   └── backend/               FastAPI commercial and infrastructure control plane
├── platform/
│   ├── ithute-auth/           identity, SSO, MFA and passkeys
│   ├── ithute-push/           push delivery platform
│   ├── ithute-realtime/       WebSocket/chat/realtime platform
│   └── ithute-notification/   deferred multi-channel notification gateway
├── engines/
│   ├── rust-core/             memory-safe native engine
│   ├── go-worker/             concurrent/network worker
│   ├── cpp-native/            benchmark-gated native hot paths
│   └── java-worker/           enterprise XML/report integration worker
├── mail/                      isolated Ithute mail runtime assets
├── infrastructure/            Caddy, DNS and infrastructure configuration
├── contracts/                 cross-component contracts
├── docs/                      architecture and operational documentation
├── scripts/                   deployment, maintenance and verification tooling
├── .github/workflows/         CI, security, release and production operations
├── compose.production.yml     immutable-image production application stack
├── compose.backup.yml         backup/restore assurance stack
├── compose.telemetry.yml      telemetry support
└── SECURITY.md                repository security policy
```

## Production runtime

The primary production application project is `ithute`.

Major services include:

- `ithute-web`;
- `ithute-app-api`;
- `ithute-auth`;
- `ithute-push`;
- `ithute-realtime`;
- `ithute-dns`;
- `ithute-java-worker`;
- dedicated PostgreSQL services;
- Redis services;
- Caddy edge routing.

Production uses immutable Docker images tagged with the exact Git commit SHA. `compose.production.yml` does not build application source on the VPS.

Canonical release image tags are:

```text
ithute-web:<commit-sha>
ithute-app-api:<commit-sha>
ithute-auth:<commit-sha>
ithute-push:<commit-sha>
ithute-realtime:<commit-sha>
```

The normal release path is:

```text
GitHub source
  -> CI and security checks
  -> immutable image build
  -> release image publication
  -> controlled production deployment
  -> migrations/bootstrap
  -> service health checks
  -> production readiness verification
```

The VPS therefore does not require a Git clone of the application source to run a release.

## Production isolation boundary

Ithute must remain non-destructive outside its own resources.

Production automation may manage Ithute-owned Compose projects and runtime directories only. It must not perform VPS-wide Docker prune/delete operations or remove another product's containers, images, networks, volumes or deployment directories.

The main runtime directory is:

```text
/home/administrator/ithute-platform
```

Independent mail state lives under:

```text
/home/administrator/ithute-platform-mail
```

## System owner

Fresh production bootstraps one authoritative Ithute system owner:

```text
thekoetlisi@ithute.co.ls
```

The password and production cryptographic secrets are never stored in Git.

## DNS and edge

Ithute currently serves the `ithute.co.ls` authoritative zone.

Initial nameserver configuration:

```text
ns1.ithute.co.ls -> 204.12.205.224
ns2.ithute.co.ls -> 204.12.205.224
```

Because both names are children of `ithute.co.ls`, registrar glue records are required.

Two nameserver names on one IPv4 do **not** provide infrastructure redundancy. An independent secondary DNS node on a different server/network remains an external production-readiness requirement.

Caddy provides the web/API/platform edge and imports validated customer hosting routes from controlled runtime storage.

## Mail deployment

Mail is an independent Compose project, `ithute-mail`, attached only to its private mail network and the controlled bridge required for Ithute application integration.

Mail/DNS readiness includes:

- MX;
- SPF;
- DKIM;
- DMARC;
- MTA-STS/TLS policy where configured;
- provider-controlled PTR/reverse DNS;
- deliverability checks.

PTR is controlled by the upstream IP/VPS provider and cannot be created by this repository alone.

## Backups, restore and telemetry

Ithute treats backup health as **restorability**, not merely successful file creation.

Repository automation includes backup/restore assurance, telemetry configuration and production readiness checks. A backup should not be considered healthy when restore drills are stale or failing.

The API exposes Prometheus-compatible metrics and health/readiness endpoints.

## CI/CD and operational automation

The repository contains dedicated GitHub Actions workflows for areas including:

- standalone CI;
- release images;
- production safety;
- production readiness;
- security;
- multi-engine CI;
- Auth;
- Push;
- Realtime;
- Auth/Push integration;
- Notification validation;
- platform mail;
- hosting build plane;
- hosting operations;
- backup assurance;
- telemetry;
- DNS cutover;
- mail finalization;
- owner-access recovery;
- VPS disk maintenance.

Production workflows that mutate the same Ithute runtime must share a controlled concurrency boundary.

## Commercial roadmap — Partner / Reseller Mode

The next major commercial capability is **Ithute Partner / Reseller Mode**.

It targets hosting companies, IT firms, software houses, developers, domain resellers and managed-service providers that want to keep their own brand and customer relationships while using Ithute as the infrastructure and automation platform underneath.

### Partner workspace

A partner should receive an isolated workspace with:

- users and delegated roles;
- white-label branding;
- custom customer portal hostname;
- partner-owned packages and pricing;
- customer organisations;
- audit history;
- wholesale and retail commercial views.

White labelling changes presentation only; platform security and isolation remain centrally enforced.

### Bring-your-own infrastructure

Partners should be able to connect multiple VPS or dedicated-server nodes.

For each node Ithute should track:

- provider/region;
- CPU and RAM;
- physical storage;
- reserved platform capacity;
- safely sellable capacity;
- infrastructure cost;
- health;
- utilisation;
- customer/service allocations;
- backup/restore state.

Raw storage must not equal sellable storage. Ithute should reserve configurable operational headroom before capacity becomes commercially allocatable.

Example:

```text
Physical storage:           142 GB
Reserved platform space:     22 GB
Sellable capacity:          120 GB
Monthly infrastructure:    M170
Target monthly revenue:   M1,200
Target gross contribution: M1,030
```

These are example values only. Costs, prices, margins, taxes and discounts remain configurable.

### Managed reseller packages

Partners should be able to combine:

- websites;
- application hosting;
- mailboxes;
- MySQL/PostgreSQL databases;
- DNS/domain services;
- SSL/TLS;
- Git/ZIP deployment;
- backups;
- monitoring;
- storage/bandwidth quotas;
- support/SLA levels.

The commercial product is a managed service, not merely raw disk space.

### Automated provisioning

A reseller sale should be able to flow through:

```text
package/order
   -> capacity + policy validation
   -> eligible node selection
   -> quota reservation
   -> hosting/mail/database/DNS provisioning
   -> customer binding
   -> billing record
   -> audit event
   -> monitoring + backup state
```

### Wholesale capacity pools

Ithute should also support reseller pools such as:

```text
Partner: Zeecom Technologies
Wholesale pool: 500 GB
Allocated: 318 GB
Available: 182 GB
Partner fee: configurable
Retail customers: partner-managed
Retail pricing: partner-managed
Branding: partner-managed
```

Zeecom Technologies is an example target profile only. The feature must remain generic for any authorized partner.

### Commercial intelligence

Partner, package, customer and node dashboards should connect technical usage with business performance:

- infrastructure cost;
- recurring revenue;
- gross contribution;
- gross margin;
- break-even utilisation;
- revenue per GB;
- revenue per node;
- allocated vs available capacity;
- most profitable packages;
- customer concentration;
- overdue or expiring services.

The commercial goal is:

> **Partners keep their brand, pricing and customer relationships. Ithute provides the infrastructure control plane, provisioning, hosting, mail, DNS, databases, billing, monitoring, security and commercial intelligence underneath.**

## Security principles

Security design across the repository follows these rules:

- strict tenant and partner scoping;
- least-privilege authorization;
- centralized identity with signed short-lived tokens;
- no direct cross-product database access;
- production secrets outside Git;
- protected node credentials;
- encrypted sensitive data where required;
- safe proxy/header handling;
- anti-cross-site mutation controls;
- secure response headers;
- auditability;
- dual control for sensitive operations;
- explicit destructive-action approval;
- no unrestricted reseller host access;
- recoverable backups;
- CI-enforced deployment boundaries.

See `SECURITY.md` and component-specific documentation for detailed controls.

## Production readiness

A merge is not the same as a verified production release.

Final readiness should confirm:

- Web, API, Auth, Push and Realtime health;
- current database migrations;
- authoritative DNS over UDP and TCP;
- TLS and correct edge routing;
- MX/SPF/DKIM/DMARC and provider-controlled PTR;
- backup plus recent restore drill;
- finance/delegated-role boundaries;
- hosting placement and node health;
- customer provisioning path;
- billing/quotation path;
- live end-to-end authentication and service use.

Use:

```bash
scripts/verify-production-readiness.sh
```

for repository-supported public checks.

## Local development

Frontend:

```bash
cd apps/frontend
npm ci
npm run build
npm run dev
```

Backend and platform services have their own requirements, migrations and component-specific documentation under `apps/backend`, `platform/` and `engines/`.

## Production configuration

`.env.example` is a configuration reference only.

Production secrets belong in protected runtime configuration and the untracked secrets store. Fresh bootstrap generates independent database passwords, encryption keys and JWT signing material.

Push deliberately does not require Firebase to make the clean platform healthy. FCM becomes required only when explicitly enabled for the Android delivery rollout.

## Documentation

For deeper implementation details, consult:

- `platform/README.md`;
- `engines/README.md`;
- `platform/ithute-auth/README.md`;
- `platform/ithute-push/README.md`;
- `platform/ithute-realtime/README.md`;
- `platform/ithute-notification/README.md`;
- `SECURITY.md`;
- `docs/`;
- `scripts/`.

---

Ithute is no longer only a website, mailbox application or DNS server. The repository now represents a **multi-tenant commercial hosting and infrastructure platform** designed to operate direct services and, increasingly, to become the underlying operating platform for other service providers.
