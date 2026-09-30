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
