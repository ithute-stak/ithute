# Ithute

Ithute is a **standalone deployment** for the Ithute website and Ithute-owned platform services. It does not join LoanHub, NBros, Tutor, Pay, Mailbox-DNS, or any other product Docker network, and it does not reuse their containers, databases, images, or volumes.

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

## System owner

Fresh production bootstraps one authoritative Ithute system owner:

```text
thekoetlisi@ithute.co.ls
```

The password is never stored in Git. `scripts/bootstrap-vps.sh` requests it interactively, writes it only to the VPS runtime `.env.production` with mode `0600`, and Auth synchronizes the account on startup. The account is active, email-verified and platform-admin.

## Fresh VPS deployment

Perform the one-time Docker/directory reset explicitly on the VPS, then run the clean bootstrap script. The destructive reset is deliberately not embedded in routine deployment automation.

After the host is clean, run as `administrator`:

```bash
curl -fsSL https://raw.githubusercontent.com/ithute-stak/ithute/main/scripts/bootstrap-vps.sh -o /tmp/bootstrap-vps.sh
chmod 700 /tmp/bootstrap-vps.sh
/tmp/bootstrap-vps.sh
```

The bootstrap script refuses to run while the retired `ithute-edge` or `mailbox-dns` directories still exist. It prompts for the system-owner password without echoing it. Do not put that password on a command line or in shell history.

After the first fresh deployment, normal GitHub deployment updates only `/home/administrator/ithute` and the `ithute` Compose project. It never performs the global wipe again.

## Mail-only domains

Mail is a separate Docker Compose project, `ithute-mail`, with its own network and host storage under `/home/administrator/ithute-mail`. It does not join the Ithute application networks.

The fresh deployment provisions these mailboxes:

```text
info@ithute.co.ls
info@lelefadebtcollectors.co.ls
info@lelefachambers.co.ls
info@tjekatjeka.co.ls
```

`ithute.co.ls` remains the Ithute website as well as a mail domain. The other requested domains are not added to Caddy and therefore are not served as Ithute websites.

The mail provisioning script writes two root-readable files on the VPS:

- `/home/administrator/ithute-mail/mailbox-credentials.txt`
- `/home/administrator/ithute-mail/mail-dns-required.txt`

Docker can configure the mail server and accounts, but public DNS is authoritative outside Docker. For Internet mail delivery each domain still needs its MX/SPF/DKIM/DMARC records applied at its DNS provider, and the VPS reverse-DNS/PTR should identify the mail host. The generated DNS file contains the required records and the generated DKIM material.

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
