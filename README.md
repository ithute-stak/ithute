# Ithute

Ithute is a **standalone deployment** for the Ithute website and Ithute-owned platform services. It does not join LoanHub, NBros, Tutor, Pay, or any other product Docker network, and it does not reuse or delete their containers, databases, images, volumes, or deployment directories.

## Runtime

The production application project is `ithute`:

- `ithute-web` — `https://ithute.co.ls`
- `ithute-app-api` — the FastAPI application behind `/api/v1`, including Mail, DNS, Hosting, Billing, Finance and Business Operations APIs
- `ithute-auth` — `https://auth.ithute.co.ls`
- `ithute-push` — `https://push.ithute.co.ls`
- `ithute-realtime` — `https://realtime.ithute.co.ls`
- `ithute-dns` — authoritative DNS for the `ithute.co.ls` zone on TCP/UDP 53
- dedicated application, Auth, Push and Realtime PostgreSQL services
- dedicated application and Realtime Redis services
- a Caddy instance that routes **only** Ithute hostnames

`compose.production.yml` contains **no application build contexts**. Production uses immutable Docker images tagged with the exact Git commit SHA.

## Authoritative DNS and registrar delegation

Ithute serves its own authoritative `ithute.co.ls` zone from the production infrastructure. The initial single-node deployment uses:

```text
ns1.ithute.co.ls -> 204.12.205.224
ns2.ithute.co.ls -> 204.12.205.224
```

Because both nameservers are children of `ithute.co.ls`, the `.ls` parent cannot discover their addresses from the child zone until the registrar/reseller publishes **glue records**. At the domain reseller, register both child nameserver/host records above, then delegate `ithute.co.ls` to:

```text
ns1.ithute.co.ls
ns2.ithute.co.ls
```

The production zone also publishes the apex, `www`, `auth`, `push`, `realtime`, and `mail` A records, together with Ithute MX/SPF/DMARC/CAA policy records. CI validates the authoritative seed before merge.

Two nameserver names on one IPv4 are **not infrastructure redundancy**. Production readiness therefore treats independent secondary DNS as an external infrastructure requirement: `ns2.ithute.co.ls` should ultimately run on a different server/network and receive the zone through an approved replicated/transfer mechanism. The repository cannot manufacture that independent network from the primary VPS.

## Build once in GitHub, run on the VPS

Application source is compiled and packaged only on GitHub Actions runners. `Ithute Standalone CI` validates the frontend, backend and deployment boundary, and builds these five application images:

```text
ithute-web:<commit-sha>
ithute-app-api:<commit-sha>
ithute-auth:<commit-sha>
ithute-push:<commit-sha>
ithute-realtime:<commit-sha>
```

Release automation publishes immutable commit-SHA images. Production deployment loads/runs the exact release images and starts the Compose project with `--no-build`.

The VPS does **not** need the Git repository, `apps/`, `platform/`, Node.js source, Python source, `npm`, or `pip` to deploy Ithute. It only needs Docker/Compose, runtime configuration, secrets and persistent volumes.

Production runtime files live under:

```text
/home/administrator/ithute-platform
```

The required application runtime files are limited to items such as:

```text
.env.production
.image.env
.ithute-bootstrapped
compose.production.yml
infrastructure/caddy/Caddyfile
infrastructure/dns/named.conf
infrastructure/dns/zones/db.ithute.co.ls
secrets/
```

A directory that still contains `apps/`, `platform/` or `.git` is legacy material from the former source-based deployment. The current Compose/deployment path does not use those directories.

Independent mail state lives under:

```text
/home/administrator/ithute-platform-mail
```

## System owner

Fresh production bootstraps one authoritative Ithute system owner:

```text
thekoetlisi@ithute.co.ls
```

The password is never stored in Git. Protected production secrets are written only to protected runtime storage. Auth synchronizes the account on startup. The account is active, email-verified and platform-admin.

## Safe VPS bootstrap

`Safe Ithute VPS Bootstrap` is manual and intended only for a new production runtime. It builds the application images on the GitHub runner, transfers runtime configuration, loads the images on the VPS and generates production secrets. It does **not** clone the repository onto the VPS.

The bootstrap is intentionally non-destructive outside Ithute. It does not run VPS-wide Docker container/image/volume deletion, Docker prune operations, or delete/move other product deployment directories.

After bootstrap creates both:

```text
/home/administrator/ithute-platform/.env.production
/home/administrator/ithute-platform/.ithute-bootstrapped
```

normal production release/deployment procedures may be used.

All production workflows that mutate the VPS must share the same Ithute production concurrency boundary so application deployment, bootstrap and mail finalization cannot modify Ithute production simultaneously.

## Deployment safety boundary

CI rejects deployment scripts that contain VPS-wide Docker deletion/prune commands or VPS-side Git clone/fetch/reset operations. It also rejects application `build:` contexts in `compose.production.yml` and source directories in the production runtime bundle.

The Ithute deployment may manage the `ithute` and `ithute-mail` Compose projects only. LoanHub, NBros, Tutor, Pay and other repositories manage their own runtime resources independently.

Routine application deployment follows this path:

```text
GitHub source
  -> CI tests
  -> immutable Docker build on GitHub runner
  -> release images
  -> controlled VPS deployment
  -> database migrations
  -> service health checks
  -> live readiness verification
```

## Backups and restore assurance

Backup readiness means **restorability**, not merely the existence of dump files. `Backup Assurance CI` performs a real backup and restores it into an isolated PostgreSQL restore-drill database. Production backup assurance also records backup and restore-drill status for operational health reporting.

Do not mark backup health as complete if restore drills are stale or failing.

## Mail-only domains

Mail is a separate Docker Compose project, `ithute-mail`, with its own host storage under `/home/administrator/ithute-platform-mail`. Mail attaches only to its private mail network and the controlled Ithute application bridge required for internal application-to-mail traffic.

The deployment provisions these mailboxes when public mail DNS is ready:

```text
info@ithute.co.ls
info@lelefadebtcollectors.co.ls
info@lelefachambers.co.ls
info@tjekatjeka.co.ls
```

`ithute.co.ls` remains the Ithute website as well as a mail domain. The other requested domains are not added to Caddy and therefore are not served as Ithute websites.

The mail provisioning process writes protected operational files under `/home/administrator/ithute-platform-mail`.

Ithute is authoritative for the `ithute.co.ls` DNS zone. Other mail-only domains remain authoritative wherever their registrars currently delegate them unless separately migrated to Ithute DNS. Their MX/SPF/DKIM/DMARC records must be correct at their authoritative DNS providers. The public IPv4 reverse-DNS/PTR must also identify the intended Ithute mail hostname; PTR is controlled by the IP/VPS provider and cannot be created by this repository alone.


## Commercial roadmap — Partner / Reseller Mode

The next major commercial capability is **Ithute Partner / Reseller Mode**. It is designed for hosting companies, IT firms, web developers, software houses, domain resellers and managed-service providers that want to sell hosting, email, applications and infrastructure under their own brand while using Ithute as the platform underneath.

The model is B2B-first: a partner keeps its brand, pricing and customer relationship while Ithute provides the operational control plane.

### Partner workspace and white labelling

Each partner should receive an isolated reseller workspace with:

- organisation profile, users, roles and delegated permissions;
- logo, colours, support identity and customer-facing service name;
- custom portal hostname;
- configurable notification identity;
- partner-owned service catalogue, package names and pricing;
- customer organisations and end-user accounts;
- complete audit history for provisioning, billing and infrastructure actions.

White labelling changes presentation only. Authentication, authorisation, tenant isolation, secret handling and audit controls remain platform-enforced.

### Bring-your-own infrastructure

A partner can connect one or more VPS or dedicated-server nodes to a private infrastructure pool. Each node should record:

- provider and region;
- CPU, RAM and physical storage;
- reserved system capacity and sellable capacity;
- operating cost and billing cycle;
- supported workloads and database engines;
- health, utilisation and availability state;
- customer allocations;
- backup and restore status.

Commercial capacity must be calculated from **usable capacity**, not raw disk size. Configurable headroom is reserved for the operating system, containers, databases, logs, temporary files, backups and operational safety.

Example:

```text
Physical storage:           142 GB
Reserved platform space:     22 GB
Sellable capacity:          120 GB
Monthly infrastructure:    M170
Target monthly revenue:   M1,200
Target gross contribution: M1,030
```

These are examples only. Costs, margins, taxes, discounts and price books must be configurable.

### Reseller service catalogue

Partners should be able to sell managed packages that combine:

- website hosting;
- application/container hosting;
- business email and mailbox quotas;
- MySQL and PostgreSQL databases;
- DNS and domain services;
- SSL/TLS automation;
- Git or ZIP deployment;
- backups and restore points;
- monitoring and uptime checks;
- storage and bandwidth allowances;
- support/SLA levels;
- optional dedicated compute.

A package therefore represents a **managed service**, not merely raw disk space.

### Customer and sub-account management

Each partner can create customer organisations containing users, domains, mailboxes, websites, applications, databases, allocations, quotations, invoices, payment records, support requests and usage history.

The partner controls what end customers can see. Ithute platform access remains role-scoped and auditable.

### Automated provisioning and placement

When a partner sells a package, Ithute should:

1. validate available capacity and policy;
2. select an eligible infrastructure node;
3. reserve the required quotas;
4. provision hosting, mail, database and DNS resources;
5. attach resources to the correct partner and customer;
6. create billing records;
7. record the provisioning audit trail;
8. start health, capacity and backup monitoring.

Placement must consider capacity, compatibility, reserved headroom and failure-domain policy.

### Commercial intelligence

At node, partner, customer and package level, Ithute should track:

- infrastructure cost;
- allocated and available capacity;
- recurring and one-off revenue;
- estimated gross contribution;
- gross margin percentage;
- revenue per GB and per node;
- customer concentration;
- utilisation;
- break-even utilisation;
- expiring or unpaid services.

The dashboard should answer:

```text
How much does this node cost?
How much capacity is safely sellable?
How much revenue is allocated to it?
Has the node reached break-even?
Which packages are most profitable?
Which customer consumes the most capacity?
Where should the next workload be placed?
```

### Wholesale capacity pools

Ithute should support wholesale reseller pools in addition to retail packages.

Example:

```text
Partner: Zeecom Technologies
Wholesale pool: 500 GB
Allocated: 318 GB
Available: 182 GB
Partner monthly fee: configurable
Retail customers: partner-managed
Retail pricing: partner-managed
Branding: partner-managed
```

Zeecom Technologies is an example target customer profile; the capability must remain generic for any authorised reseller.

Wholesale pools require enforced quotas so a reseller cannot exceed contracted capacity without an approved upgrade or configured burst policy.

### Billing, quotations and invoicing

Partner / Reseller Mode should integrate with Ithute Billing and Finance and support:

- monthly, quarterly and annual billing;
- setup and migration fees;
- wholesale and retail price books;
- discounts and negotiated pricing;
- quotations that convert into subscriptions;
- invoices, statements and credit adjustments;
- taxes and configurable currencies;
- payment status and ageing;
- controlled suspension and reactivation policies.

Ithute administrators should see platform revenue from the partner while the partner separately sees its own retail revenue and margin.

### Security and isolation requirements

Partner / Reseller Mode is complete only when it preserves production-grade isolation:

- strict partner and tenant scoping;
- least-privilege RBAC;
- separate customer secrets and credentials;
- encrypted secret storage;
- auditable infrastructure actions;
- no cross-partner resource visibility;
- rate limits and abuse controls;
- safe suspension and deletion workflows;
- backup and restore ownership boundaries;
- explicit approval for destructive actions.

Connecting infrastructure must not give a reseller unrestricted access to the host. Ithute should expose only the operational capabilities required for provisioning, monitoring and lifecycle management.

### Partner dashboard

A partner dashboard should combine infrastructure and business performance:

```text
Customers:                 327
Hosting accounts:          246
Mailboxes:               1,820
Connected nodes:             8
Total usable capacity:    7.4 TB
Allocated:                4.8 TB
Available:                2.6 TB
Monthly infrastructure:   Mxx,xxx
Monthly customer revenue: Mxx,xxx
Gross contribution:       Mxx,xxx
Gross margin:                  xx%
```

### Commercial outcome

This feature moves Ithute from serving only direct customers into a **hosting operating system for other service providers**.

> Partners keep their brand, pricing and customer relationships. Ithute provides the infrastructure control plane, provisioning, hosting, mail, DNS, databases, billing, monitoring, security and commercial intelligence underneath.

This allows one Ithute platform to serve direct customers, wholesale customers and white-label resellers while keeping infrastructure, tenant isolation and financial visibility under one controlled system.


## Production readiness

A release is not considered fully verified merely because it has merged. Final production verification should confirm:

- application, Auth, Push and Realtime health endpoints;
- current Alembic migration head applied successfully;
- authoritative DNS answers over both UDP and TCP;
- TLS and explicit host routing;
- mail MX/SPF/DKIM/DMARC and provider-controlled PTR/reverse DNS;
- successful backup plus a recent restore drill;
- Finance delegated-role boundaries and customer portal access;
- a live end-to-end customer path covering authentication, provisioning, billing/Finance and the relevant service.

Use `scripts/verify-production-readiness.sh` for the repository-supported public checks. External requirements such as an independent secondary DNS node and provider-controlled PTR must be completed with the appropriate infrastructure provider.

## Local website

```bash
cd apps/frontend
npm ci
npm run check
npm run build
npm run dev
```

## Production configuration

Copy `.env.example` only as a reference. Production secrets live exclusively in protected runtime storage and the untracked `secrets/` directory.

The fresh bootstrap generates independent database passwords, encryption keys and JWT signing keys. Push starts without a mandatory FCM provider so the platform can become healthy on a clean server; FCM can be enabled later by installing its service-account credential and setting `ITHUTE_PUSH_REQUIRED_PROVIDERS=fcm`.
