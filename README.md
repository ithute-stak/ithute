# Ithute

Ithute is a **standalone deployment** for the Ithute website and Ithute-owned platform services. It does not join LoanHub, NBros, Tutor, Pay, Mailbox-DNS, or any other product Docker network, and it does not reuse or delete their containers, databases, images, volumes, or deployment directories.

## Runtime

The production application project is `ithute`:

- `ithute-web` — `https://ithute.co.ls`
- `ithute-auth` — `https://auth.ithute.co.ls`
- `ithute-push` — `https://push.ithute.co.ls`
- `ithute-realtime` — `https://realtime.ithute.co.ls`
- dedicated Auth, Push and Realtime PostgreSQL services
- dedicated Realtime Redis
- a Caddy instance that routes **only** Ithute hostnames

`compose.production.yml` contains **no application build contexts**. Production uses immutable Docker images tagged with the exact Git commit SHA.

## Build once in GitHub, run on the VPS

Application source is compiled and packaged only on GitHub Actions runners. `Ithute Standalone CI` performs the frontend checks, validates the deployment boundary, builds these four Docker images and packages the exact tested images as a workflow artifact:

```text
ithute-web:<commit-sha>
ithute-auth:<commit-sha>
ithute-push:<commit-sha>
ithute-realtime:<commit-sha>
```

`Deploy Ithute Production` downloads that image artifact from the successful CI run, verifies its SHA-256 checksum, transfers the compressed Docker image bundle to the VPS, runs `docker load`, uploads only the small runtime configuration bundle, and starts the Compose project with `--no-build`.

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
.deployed-sha
compose.production.yml
infrastructure/caddy/Caddyfile
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

The password is never stored in Git. GitHub Actions provides the protected production secret to the one-time bootstrap, which writes it only to the VPS runtime `.env.production` with mode `0600`. Auth synchronizes the account on startup. The account is active, email-verified and platform-admin.

## Safe VPS bootstrap

`Safe Ithute VPS Bootstrap` is manual and intended only for a new production runtime. It builds the application images on the GitHub runner, transfers the Docker image bundle and runtime configuration, loads the images on the VPS and generates the production secrets. It does **not** clone the repository onto the VPS.

The bootstrap is intentionally non-destructive outside Ithute. It does not run VPS-wide Docker container/image/volume deletion, Docker prune operations, or delete/move other product deployment directories.

After bootstrap creates both:

```text
/home/administrator/ithute-platform/.env.production
/home/administrator/ithute-platform/.ithute-bootstrapped
```

normal successful `main` CI runs are deployed automatically by `Deploy Ithute Production`.

All production workflows that mutate the VPS share the same `ithute-vps-production` concurrency group so application deployment, bootstrap and mail finalization cannot modify Ithute production simultaneously.

## Deployment safety boundary

CI rejects deployment scripts that contain VPS-wide Docker deletion/prune commands or VPS-side Git clone/fetch/reset operations. It also rejects application `build:` contexts in `compose.production.yml` and source directories in the production runtime bundle.

The Ithute deployment may manage the `ithute` and `ithute-mail` Compose projects only. LoanHub, NBros, Tutor, Pay and other repositories manage their own runtime resources independently.

Routine application deployment follows this path:

```text
GitHub source
  -> CI tests
  -> Docker build on GitHub runner
  -> tested image artifact
  -> SCP image artifact to VPS
  -> docker load
  -> docker compose up --no-build
```

## Mail-only domains

Mail is a separate Docker Compose project, `ithute-mail`, with its own network and host storage under `/home/administrator/ithute-platform-mail`. It does not join the Ithute application network.

Mail finalization also avoids a repository checkout on the VPS. GitHub Actions transfers only the transient mail runtime templates needed for provisioning; persistent mail configuration and data remain in `/home/administrator/ithute-platform-mail`.

The deployment provisions these mailboxes when public mail DNS is ready:

```text
info@ithute.co.ls
info@lelefadebtcollectors.co.ls
info@lelefachambers.co.ls
info@tjekatjeka.co.ls
```

`ithute.co.ls` remains the Ithute website as well as a mail domain. The other requested domains are not added to Caddy and therefore are not served as Ithute websites.

The mail provisioning script writes two protected files on the VPS:

- `/home/administrator/ithute-platform-mail/mailbox-credentials.txt`
- `/home/administrator/ithute-platform-mail/mail-dns-required.txt`

Docker can configure the mail server and accounts, but public DNS is authoritative outside Docker. For Internet mail delivery each domain still needs its MX/SPF/DKIM/DMARC records applied at its DNS provider, and the VPS reverse-DNS/PTR should identify the mail host.

## Local website

```bash
cd apps/frontend
npm ci
npm run check
npm run build
npm run dev
```

## Production configuration

Copy `.env.example` only as a reference. Production secrets live exclusively in `.env.production` on the VPS and in the untracked `secrets/` directory.

The fresh bootstrap generates independent database passwords, encryption keys and JWT signing keys. Push starts without a mandatory FCM provider so the platform can become healthy on a clean server; FCM can be enabled later by installing its service-account credential and setting `ITHUTE_PUSH_REQUIRED_PROVIDERS=fcm`.
