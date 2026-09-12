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

The public site and every platform service are built as separate Docker images from this repository. `compose.production.yml` declares no external Docker network and no external named volume.

Production files live under:

```text
/home/administrator/ithute-platform
```

Independent mail state lives under:

```text
/home/administrator/ithute-platform-mail
```

These paths intentionally avoid historical deployment directories that may have different ownership or belong to retired layouts.

## System owner

Fresh production bootstraps one authoritative Ithute system owner:

```text
thekoetlisi@ithute.co.ls
```

The password is never stored in Git. GitHub Actions provides the protected production secret to the one-time bootstrap, which writes it only to the VPS runtime `.env.production` with mode `0600`. Auth synchronizes the account on startup. The account is active, email-verified and platform-admin.

## Safe VPS bootstrap

The `Safe Ithute VPS Bootstrap` workflow performs the initial deployment. It is intentionally **non-destructive outside Ithute**. It does not run VPS-wide Docker container/image/volume deletion, Docker prune operations, or delete/move other product deployment directories.

The bootstrap creates or updates only the isolated Ithute application directory, the `ithute` Docker Compose project, and the separate `ithute-mail` project when mail DNS is ready.

After bootstrap creates both:

```text
/home/administrator/ithute-platform/.env.production
/home/administrator/ithute-platform/.ithute-bootstrapped
```

normal successful `main` CI runs are deployed by `Deploy Ithute Production`.

All production workflows that mutate the VPS share the same `ithute-vps-production` concurrency group so application deployment, bootstrap and mail finalization cannot modify Ithute production simultaneously.

## Deployment safety boundary

CI rejects deployment scripts that contain VPS-wide Docker deletion/prune commands. The Ithute deployment may manage the `ithute` and `ithute-mail` Compose projects only. LoanHub, NBros, Tutor, Pay and other repositories must manage their own runtime resources independently.

Routine deployment never removes another repository's containers, images, networks, volumes or data.

## Mail-only domains

Mail is a separate Docker Compose project, `ithute-mail`, with its own network and host storage under `/home/administrator/ithute-platform-mail`. It does not join the Ithute application network.

The fresh deployment provisions these mailboxes when public mail DNS is ready:

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

Docker can configure the mail server and accounts, but public DNS is authoritative outside Docker. For Internet mail delivery each domain still needs its MX/SPF/DKIM/DMARC records applied at its DNS provider, and the VPS reverse-DNS/PTR should identify the mail host. The generated DNS file contains the required records and generated DKIM material.

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

The fresh script generates new independent database passwords, encryption keys and JWT signing keys. Push starts without a mandatory FCM provider so the platform can become healthy on a clean server; FCM can be enabled later by installing its service-account credential and setting `ITHUTE_PUSH_REQUIRED_PROVIDERS=fcm`.