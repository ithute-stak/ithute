# Ithute production release process

Ithute production is operator-controlled. GitHub validates and publishes immutable application images, but GitHub must not SSH into the production VPS or change running production services during a normal release.

## Release flow

1. Merge tested changes into `main`.
2. `Ithute Standalone CI` must complete successfully for that exact commit.
3. `Production Safety CI` must complete successfully for that exact commit.
4. `Ithute Release Images` publishes all seven application images to GHCR using the exact commit SHA:
   - `ghcr.io/ithute-stak/ithute-web:<sha>`
   - `ghcr.io/ithute-stak/ithute-app-api:<sha>`
   - `ghcr.io/ithute-stak/ithute-go-worker:<sha>`
   - `ghcr.io/ithute-stak/ithute-java-worker:<sha>`
   - `ghcr.io/ithute-stak/ithute-auth:<sha>`
   - `ghcr.io/ithute-stak/ithute-push:<sha>`
   - `ghcr.io/ithute-stak/ithute-realtime:<sha>`
5. Confirm the release-image workflow is green.
6. Production remains unchanged until an operator logs into the VPS and explicitly deploys that exact SHA.

A green CI result alone is not a deployable production release. Both CI gates and image publication must succeed for the same SHA.

## Production directory

The established Ithute production directory is:

```text
/home/administrator/ithute-platform
```

The deployment helper intentionally refuses to operate outside this directory.

## One-time VPS setup

Install the checked-in helper at:

```text
/home/administrator/ithute-platform/scripts/deploy-production-manual.sh
```

and make it executable:

```bash
chmod 700 /home/administrator/ithute-platform/scripts/deploy-production-manual.sh
```

The VPS must already contain the existing persistent Ithute state, including `.ithute-bootstrapped`, `.env.production`, secrets, databases, volumes, and the current runtime files.

Authenticate Docker to GHCR using an account/token that can read the Ithute packages:

```bash
sudo docker login ghcr.io
```

Enter the token interactively. Do not put package credentials in the repository or shell history.

## Deploy an exact tested release

```bash
cd /home/administrator/ithute-platform
sudo ./scripts/deploy-production-manual.sh <40-character-release-sha>
```

The helper does not use a mutable `latest` Docker tag. It keeps the currently running release available for rollback, checks disk/inode headroom, pulls the candidate and rollback image sets from GHCR, retrieves only the exact SHA-pinned runtime configuration, and invokes the existing rollback-safe `scripts/deploy-production.sh` engine. That engine continues to validate Compose, PowerDNS, Caddy, Auth, App API, Web, Push, Realtime, public endpoints, and last-known-good state.

If the requested SHA is already recorded in `.image.env`, the helper exits successfully without pulling, migrating, restarting, or redeploying anything.

## Global pull command

Install the checked-in evergreen launcher once:

```bash
cd /home/administrator/ithute-platform
sudo bash scripts/install-production-pull-command.sh
```

This installs:

```text
/usr/local/bin/pull
```

After that, deploy with:

```bash
pull ithute latest
```

The launcher is intentionally tiny. On every invocation it resolves the exact current `main` SHA, downloads `scripts/deploy-production-latest.sh` from that exact commit, syntax-checks it, and executes that fresh launcher. This prevents a stale VPS copy of the global `pull` command from silently using an outdated image list or deployment contract.

`latest` must mean the current `main` SHA only after `Ithute Standalone CI`, `Production Safety CI`, and `Ithute Release Images` all succeeded for that exact SHA. The exact deployment helper must include the complete seven-image production bundle: Web, App API, Go worker, Java worker, Auth, Push, and Realtime. If `.image.env` already contains that SHA, the command must stop without redeploying.

Never choose the most recently listed successful workflow run without comparing it to current `main`; old successful runs may appear later in the Actions API and are not necessarily newer code.
