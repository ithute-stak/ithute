#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
ENV_FILE="${ITHUTE_ENV_FILE:-$APP_DIR/.env.production}"
IMAGE_ENV_FILE="${ITHUTE_IMAGE_ENV_FILE:-$APP_DIR/.image.env}"
COMPOSE_FILE="$APP_DIR/compose.production.yml"
PROJECT_NAME="ithute"
CUTOVER_MARKER="$APP_DIR/.dns-cutover-complete"

cd "$APP_DIR"

test -f "$ENV_FILE" || { echo "Missing $ENV_FILE. Run the safe bootstrap once first." >&2; exit 2; }
test -f "$COMPOSE_FILE" || { echo "Missing $COMPOSE_FILE" >&2; exit 2; }
test -f "$APP_DIR/infrastructure/caddy/Caddyfile" || { echo "Missing Caddyfile" >&2; exit 2; }
test -f "$APP_DIR/infrastructure/dns/zones/db.ithute.co.ls" || { echo "Missing Ithute DNS seed zone" >&2; exit 2; }
test -f "$APP_DIR/secrets/ithute-auth/jwt-private.pem" || { echo "Missing Auth private key" >&2; exit 2; }
test -f "$APP_DIR/secrets/ithute-auth/jwt-public.pem" || { echo "Missing Auth public key" >&2; exit 2; }

# The restored Mail/DNS control plane has its own persistent secrets and
# database credentials. Generate them once on the VPS and preserve them across
# immutable image deployments. Values are never printed to Actions logs.
python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import json
import secrets
import sys

path = Path(sys.argv[1])
required = (
    "ITHUTE_APP_DB_PASSWORD",
    "ITHUTE_APP_SECRET_KEY",
    "ITHUTE_APP_DKIM_ENCRYPTION_KEY",
    "ITHUTE_APP_BILLING_WEBHOOK_SECRET",
    "ITHUTE_APP_BOOTSTRAP_ADMIN_PASSWORD",
    "ITHUTE_APP_MAIL_OPS_TOKEN",
    "ITHUTE_APP_MAIL_NODE_TOKEN",
    "ITHUTE_APP_RECOVERY_OPS_TOKEN",
    "ITHUTE_APP_POWERDNS_API_KEY",
)

lines = path.read_text(encoding="utf-8").splitlines()
values = {}
for line in lines:
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

for key in required:
    if not values.get(key):
        values[key] = secrets.token_urlsafe(48)

clients_key = "ITHUTE_AUTH_FIRST_PARTY_CLIENTS"
clients = values.get(clients_key, "")
if not clients:
    clients = "ithute-realtime:!thute Realtime"
if "mailbox-dns:" not in clients:
    clients = f"{clients},mailbox-dns:Mailbox DNS"
values[clients_key] = clients

redirect_key = "ITHUTE_AUTH_REDIRECT_URIS_JSON"
try:
    redirects = json.loads(values.get(redirect_key) or "{}")
except json.JSONDecodeError:
    redirects = {}
if not isinstance(redirects, dict):
    redirects = {}
mailbox_redirect = "https://ithute.co.ls/api/v1/auth/ithute/callback"
existing = redirects.get("mailbox-dns")
if not isinstance(existing, list):
    existing = []
if mailbox_redirect not in existing:
    existing.append(mailbox_redirect)
redirects["mailbox-dns"] = existing
values[redirect_key] = json.dumps(redirects, separators=(",", ":"))

managed = set(required) | {clients_key, redirect_key}
kept = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in managed:
            continue
    kept.append(line)
if kept and kept[-1].strip():
    kept.append("")
kept.append("# Restored Ithute Mail/DNS control-plane runtime")
for key in required:
    kept.append(f"{key}={values[key]}")
kept.append(f"{clients_key}={values[clients_key]}")
kept.append(f"{redirect_key}={values[redirect_key]}")
path.write_text("\n".join(kept) + "\n", encoding="utf-8")
PY
chmod 600 "$ENV_FILE"

if [ -n "${ITHUTE_IMAGE_TAG:-}" ]; then
  case "$ITHUTE_IMAGE_TAG" in
    *[!0-9a-f]*|'') echo "ITHUTE_IMAGE_TAG must be a lowercase Git commit SHA." >&2; exit 2 ;;
  esac
  if [ "${#ITHUTE_IMAGE_TAG}" -ne 40 ]; then
    echo "ITHUTE_IMAGE_TAG must be a full 40-character Git commit SHA." >&2
    exit 2
  fi
  umask 077
  printf 'ITHUTE_IMAGE_TAG=%s\n' "$ITHUTE_IMAGE_TAG" > "$IMAGE_ENV_FILE.tmp"
  mv "$IMAGE_ENV_FILE.tmp" "$IMAGE_ENV_FILE"
  chmod 600 "$IMAGE_ENV_FILE"
fi

test -f "$IMAGE_ENV_FILE" || { echo "Missing $IMAGE_ENV_FILE" >&2; exit 2; }
IMAGE_TAG="$(sed -n 's/^ITHUTE_IMAGE_TAG=//p' "$IMAGE_ENV_FILE" | tail -n1)"
case "$IMAGE_TAG" in
  *[!0-9a-f]*|'') echo "Invalid image tag in $IMAGE_ENV_FILE" >&2; exit 2 ;;
esac
if [ "${#IMAGE_TAG}" -ne 40 ]; then
  echo "Image tag must be a full 40-character Git commit SHA." >&2
  exit 2
fi

for image in \
  "ithute-web:$IMAGE_TAG" \
  "ithute-app-api:$IMAGE_TAG" \
  "ithute-auth:$IMAGE_TAG" \
  "ithute-push:$IMAGE_TAG" \
  "ithute-realtime:$IMAGE_TAG"
do
  docker image inspect "$image" >/dev/null 2>&1 || {
    echo "Missing prebuilt image on VPS: $image" >&2
    echo "Images must be built by GitHub Actions and loaded before deployment." >&2
    exit 2
  }
done

# Once DNS/TLS cutover has been finalized, routine deployments must never
# re-enable the temporary direct-IP route just because the repository still
# carries the propagation fallback for first bootstrap.
if [ -f "$CUTOVER_MARKER" ]; then
  sed -i '/^# BEGIN ITHUTE TEMPORARY IP FALLBACK$/,/^# END ITHUTE TEMPORARY IP FALLBACK$/d' \
    "$APP_DIR/infrastructure/caddy/Caddyfile"
fi

compose() {
  docker compose \
    --env-file "$ENV_FILE" \
    --env-file "$IMAGE_ENV_FILE" \
    -p "$PROJECT_NAME" \
    -f "$COMPOSE_FILE" \
    "$@"
}

compose config >/tmp/ithute-compose.rendered.yml
if grep -Eq 'external:[[:space:]]*true' /tmp/ithute-compose.rendered.yml; then
  echo "Refusing deployment: standalone Ithute compose contains an external Docker resource." >&2
  exit 1
fi
if grep -Eq '^[[:space:]]*build:' /tmp/ithute-compose.rendered.yml; then
  echo "Refusing deployment: production compose must use prebuilt images only." >&2
  exit 1
fi

# Pull only third-party runtime images. All Ithute application images were
# already built and tested by GitHub Actions.
compose pull \
  ithute-app-db \
  ithute-app-redis \
  ithute-app-rspamd-redis \
  ithute-auth-db \
  ithute-push-db \
  ithute-realtime-db \
  ithute-realtime-redis \
  ithute-dns \
  caddy

if ! compose up -d --remove-orphans --no-build; then
  echo "Ithute containers did not reach their Compose startup conditions." >&2
  compose ps >&2 || true
  echo "Restored app API logs:" >&2
  compose logs --tail=200 ithute-app-api >&2 || true
  echo "Authoritative DNS logs:" >&2
  compose logs --tail=200 ithute-dns >&2 || true
  exit 1
fi

# Activate uploaded Caddy runtime configuration explicitly. PowerDNS record
# changes are applied through its HTTP API and require no nameserver reload.
compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null
compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null

check_service() {
  local name="$1"
  local command="$2"
  local attempt
  for attempt in $(seq 1 60); do
    if compose exec -T "$name" sh -c "$command" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Health verification failed for $name" >&2
  compose ps
  compose logs --tail=120 "$name" >&2 || true
  return 1
}

check_service ithute-dns "python3 -c 'import os,urllib.request; request=urllib.request.Request(\"http://127.0.0.1:8081/api/v1/servers/localhost\", headers={\"X-API-Key\": os.environ[\"PDNS_AUTH_API_KEY\"]}); urllib.request.urlopen(request, timeout=3).read()'"
check_service ithute-web "wget -qO- http://127.0.0.1:3000/health | grep -q ithute-web"
check_service ithute-app-api "curl -fsS http://127.0.0.1:8000/health/ready | grep -q '\"status\":\"ready\"'"
check_service ithute-app-api "python -c 'from app.services.powerdns import PowerDNSClient; zone=PowerDNSClient().get_zone(\"ithute.co.ls\"); assert zone.get(\"name\") == \"ithute.co.ls.\"'"
check_service ithute-auth "curl -fsS http://127.0.0.1:8080/healthz | grep -q ithute-auth"
check_service ithute-push "curl -fsS http://127.0.0.1:8080/readyz | grep -q '\"status\":\"ready\"'"
check_service ithute-realtime "curl -fsS http://127.0.0.1:8080/readyz | grep -q '\"status\":\"ready\"'"

if [ "${ITHUTE_REQUIRE_PUBLIC_HEALTH:-0}" = "1" ]; then
  html="$(curl --retry 15 --retry-delay 3 --retry-all-errors -fsS https://ithute.co.ls/)"
  printf '%s' "$html" | grep -Fq 'Mail & DNS'
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://ithute.co.ls/pricing | grep -Fq 'Choose capacity'
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://ithute.co.ls/docs | grep -Fq 'Packages'
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://auth.ithute.co.ls/healthz | grep -q ithute-auth
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://push.ithute.co.ls/readyz | grep -q '\"status\":\"ready\"'
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://realtime.ithute.co.ls/readyz | grep -q '\"status\":\"ready\"'
fi

compose ps
compose images
printf '\nIthute restored application, central platform, and PowerDNS authoritative DNS are healthy.\n'
