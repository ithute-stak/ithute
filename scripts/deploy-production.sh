#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
ENV_FILE="${ITHUTE_ENV_FILE:-$APP_DIR/.env.production}"
IMAGE_ENV_FILE="${ITHUTE_IMAGE_ENV_FILE:-$APP_DIR/.image.env}"
LAST_GOOD_ENV_FILE="${ITHUTE_LAST_GOOD_ENV_FILE:-$APP_DIR/.last-known-good.env}"
LAST_GOOD_RUNTIME_ARCHIVE="${ITHUTE_LAST_GOOD_RUNTIME_ARCHIVE:-$APP_DIR/.last-known-good-runtime.tgz}"
CANDIDATE_IMAGE_ENV_FILE="$APP_DIR/.image.candidate.env"
ROLLBACK_IMAGE_ENV_FILE="$APP_DIR/.image.rollback.env"
COMPOSE_FILE="$APP_DIR/compose.production.yml"
PROJECT_NAME="ithute"
CUTOVER_MARKER="$APP_DIR/.dns-cutover-complete"
PUBLIC_EDGE_NETWORK="${PUBLIC_EDGE_NETWORK:-public-edge}"
FALLBACK_IMAGE_TAG="${ITHUTE_FALLBACK_IMAGE_TAG:-}"
REQUIRE_PUBLIC_HEALTH="${ITHUTE_REQUIRE_PUBLIC_HEALTH:-0}"

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
    "ITHUTE_PUSH_ITHUTE_GATEWAY_TOKEN",
    "ITHUTE_REALTIME_GO_GATEWAY_TOKEN",
    "ITHUTE_NATIVE_ENGINE_TOKEN",
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

configure_edge_private_network() {
  local helper="$APP_DIR/infrastructure/wireguard-edge/bootstrap.sh"
  test -f "$helper" || {
    echo "Missing managed private-network bootstrap helper: $helper" >&2
    return 1
  }
  local public_ip
  public_ip="$(sed -n 's/^ITHUTE_PUBLIC_IPV4=//p' "$ENV_FILE" | tail -n1)"
  test -n "$public_ip" || {
    echo "ITHUTE_PUBLIC_IPV4 is missing from $ENV_FILE" >&2
    return 1
  }
  ITHUTE_APP_DIR="$APP_DIR" \
  ITHUTE_ENV_FILE="$ENV_FILE" \
  ITHUTE_PUBLIC_IPV4="$public_ip" \
  ITHUTE_API_URL="https://ithute.co.ls" \
    bash "$helper"
}

verify_edge_private_network() {
  test -s /etc/ithute-wireguard/private.key || return 1
  test -s /etc/ithute-wireguard/reconciler.env || return 1
  systemctl is-active --quiet ithute-wireguard-edge-firewall.service || return 1
  systemctl is-active --quiet wg-quick@ithute0 || return 1
  systemctl is-active --quiet ithute-wireguard-edge-reconciler.timer || return 1
  local edge_address listen_port
  edge_address="$(sed -n 's/^ITHUTE_WIREGUARD_EDGE_ADDRESS=//p' "$ENV_FILE" | tail -n1)"
  listen_port="$(sed -n 's/^ITHUTE_WIREGUARD_LISTEN_PORT=//p' "$ENV_FILE" | tail -n1)"
  ip -4 -o addr show dev ithute0 | grep -Fq " $edge_address/" || return 1
  test "$(wg show ithute0 listen-port)" = "$listen_port" || return 1
}

configure_edge_private_network || exit 1
verify_edge_private_network || {
  echo "Managed private-network edge readiness failed." >&2
  exit 1
}

valid_tag() {
  local tag="${1:-}"
  [[ "$tag" =~ ^[0-9a-f]{40}$ ]]
}

require_tag() {
  local tag="$1"
  local label="$2"
  if ! valid_tag "$tag"; then
    echo "$label must be a full 40-character lowercase Git commit SHA." >&2
    return 1
  fi
}

images_present() {
  local tag="$1"
  local image
  for image in ithute-web ithute-app-api ithute-auth ithute-push ithute-realtime; do
    docker image inspect "$image:$tag" >/dev/null 2>&1 || return 1
  done
}

candidate_images_present() {
  local tag="$1"
  images_present "$tag" || return 1
  docker image inspect "ithute-go-worker:$tag" >/dev/null 2>&1 || return 1
  docker image inspect "ithute-java-worker:$tag" >/dev/null 2>&1 || return 1
}

if [ -n "${ITHUTE_IMAGE_TAG:-}" ]; then
  CANDIDATE_TAG="$ITHUTE_IMAGE_TAG"
else
  CANDIDATE_TAG="$(sed -n 's/^ITHUTE_IMAGE_TAG=//p' "$IMAGE_ENV_FILE" 2>/dev/null | tail -n1)"
fi
require_tag "$CANDIDATE_TAG" "ITHUTE_IMAGE_TAG"
candidate_images_present "$CANDIDATE_TAG" || {
  echo "Candidate image bundle is incomplete on the VPS for $CANDIDATE_TAG." >&2
  exit 2
}

ROLLBACK_TAG=""
if [ -f "$LAST_GOOD_ENV_FILE" ]; then
  stored="$(sed -n 's/^ITHUTE_IMAGE_TAG=//p' "$LAST_GOOD_ENV_FILE" | tail -n1)"
  if valid_tag "$stored" && images_present "$stored"; then
    ROLLBACK_TAG="$stored"
  fi
fi
if [ -z "$ROLLBACK_TAG" ] && valid_tag "$FALLBACK_IMAGE_TAG" && images_present "$FALLBACK_IMAGE_TAG"; then
  ROLLBACK_TAG="$FALLBACK_IMAGE_TAG"
fi

umask 077
printf 'ITHUTE_IMAGE_TAG=%s\n' "$CANDIDATE_TAG" > "$CANDIDATE_IMAGE_ENV_FILE"
chmod 600 "$CANDIDATE_IMAGE_ENV_FILE"
ACTIVE_IMAGE_ENV_FILE="$CANDIDATE_IMAGE_ENV_FILE"

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
    --env-file "$ACTIVE_IMAGE_ENV_FILE" \
    -p "$PROJECT_NAME" \
    -f "$COMPOSE_FILE" \
    "$@"
}

validate_runtime() {
  compose config >/tmp/ithute-compose.rendered.yml || return 1
  if grep -Eq 'external:[[:space:]]*true' /tmp/ithute-compose.rendered.yml; then
    echo "Refusing deployment: standalone Ithute compose contains an external Docker resource." >&2
    return 1
  fi
  if grep -Eq '^[[:space:]]*build:' /tmp/ithute-compose.rendered.yml; then
    echo "Refusing deployment: production compose must use prebuilt images only." >&2
    return 1
  fi
}

wait_service() {
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
  compose ps >&2 || true
  compose logs --tail=160 "$name" >&2 || true
  return 1
}

verify_core_health() {
  wait_service ithute-dns "python3 -c 'import os,urllib.request; request=urllib.request.Request(\"http://127.0.0.1:8081/api/v1/servers/localhost\", headers={\"X-API-Key\": os.environ[\"PDNS_AUTH_API_KEY\"]}); urllib.request.urlopen(request, timeout=3).read()'" || return 1
  wait_service ithute-auth "curl -fsS http://127.0.0.1:8080/healthz | grep -q ithute-auth" || return 1
  wait_service ithute-app-api "curl -fsS http://127.0.0.1:8000/health/ready | grep -q '\"status\":\"ready\"'" || return 1
  if compose config --services | grep -Fxq ithute-native-engine; then
    wait_service ithute-native-engine "curl -fsS http://127.0.0.1:8080/healthz | grep -q ithute-native-engine" || return 1
  fi
  if compose config --services | grep -Fxq ithute-go-worker; then
    wait_service ithute-go-worker "wget -qO- http://127.0.0.1:8080/healthz | grep -q ithute-go-worker" || return 1
  fi
  if compose config --services | grep -Fxq ithute-java-worker; then
    wait_service ithute-java-worker "wget -qO- http://127.0.0.1:8080/healthz | grep -q ithute-java-worker" || return 1
  fi
  if compose config --services | grep -Fxq ithute-hosting-health-controller; then
  wait_service ithute-hosting-health-controller "python -c 'import app.services.hosting_node_health,app.services.hosting_node_health_daemon'" || return 1
  fi
  wait_service ithute-web "wget -qO- http://127.0.0.1:3000/health | grep -q ithute-web" || return 1
  wait_service ithute-push "curl -fsS http://127.0.0.1:8080/readyz | grep -q '\"status\":\"ready\"'" || return 1
  wait_service ithute-realtime "curl -fsS http://127.0.0.1:8080/readyz | grep -q '\"status\":\"ready\"'" || return 1
  wait_service ithute-app-api "python -c 'from app.services.powerdns import PowerDNSClient; zone=PowerDNSClient().get_zone(\"ithute.co.ls\"); assert zone.get(\"name\") == \"ithute.co.ls.\"'" || return 1
}

ensure_edge_and_reload() {
  docker network inspect "$PUBLIC_EDGE_NETWORK" >/dev/null 2>&1 || docker network create "$PUBLIC_EDGE_NETWORK" >/dev/null || return 1
  local caddy_id
  caddy_id="$(compose ps -q caddy)"
  test -n "$caddy_id" || return 1
  if ! docker inspect -f '{{json .NetworkSettings.Networks}}' "$caddy_id" | grep -q "\"$PUBLIC_EDGE_NETWORK\""; then
    docker network connect "$PUBLIC_EDGE_NETWORK" "$caddy_id" || return 1
  fi
  compose exec -T caddy mkdir -p /data/product-routes || return 1
  compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null || return 1
  compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null || return 1
}

require_public_marker() {
  local label="$1"
  local url="$2"
  local expected="$3"
  local body
  body="$(curl --retry 10 --retry-delay 2 --retry-all-errors --connect-timeout 10 -fsS "$url")" || {
    echo "Public health failed: $label could not be fetched at $url" >&2
    return 1
  }
  if [[ "$body" != *"$expected"* ]]; then
    echo "Public health failed: $label did not contain expected marker: $expected" >&2
    return 1
  fi
}

verify_public_health() {
  [ "$REQUIRE_PUBLIC_HEALTH" = "1" ] || return 0
  require_public_marker 'Ithute home' 'https://ithute.co.ls/' 'One home for the systems that move organisations forward.' || return 1
  require_public_marker 'Pricing' 'https://ithute.co.ls/pricing' 'Your business online from' || return 1
  require_public_marker 'Hosting rules' 'https://ithute.co.ls/hosting-docs' 'Rules for every system hosted on Ithute.' || return 1
  require_public_marker 'Documentation' 'https://ithute.co.ls/docs' 'Public configuration manual' || return 1
  require_public_marker 'Central Auth health' 'https://auth.ithute.co.ls/healthz' 'ithute-auth' || return 1
  require_public_marker 'Push health' 'https://push.ithute.co.ls/readyz' '"status":"ready"' || return 1
  require_public_marker 'Realtime health' 'https://realtime.ithute.co.ls/readyz' '"status":"ready"' || return 1
}

dump_failure_logs() {
  echo "Candidate release $CANDIDATE_TAG failed. Container state:" >&2
  compose ps >&2 || true
  compose logs --tail=220 ithute-auth ithute-app-api ithute-go-worker ithute-java-worker ithute-web ithute-push ithute-realtime >&2 || true
}

record_last_good() {
  local tag="$1"
  umask 077
  printf 'ITHUTE_IMAGE_TAG=%s\n' "$tag" > "$LAST_GOOD_ENV_FILE.tmp"
  mv "$LAST_GOOD_ENV_FILE.tmp" "$LAST_GOOD_ENV_FILE"
  chmod 600 "$LAST_GOOD_ENV_FILE"
  tar -czf "$LAST_GOOD_RUNTIME_ARCHIVE.tmp" \
    compose.production.yml \
    infrastructure/caddy/Caddyfile \
    infrastructure/dns/zones/db.ithute.co.ls \
    infrastructure/wireguard-edge
  mv "$LAST_GOOD_RUNTIME_ARCHIVE.tmp" "$LAST_GOOD_RUNTIME_ARCHIVE"
  chmod 600 "$LAST_GOOD_RUNTIME_ARCHIVE"
}

rollback_to_last_good() {
  if [ -z "$ROLLBACK_TAG" ]; then
    echo "No healthy rollback image set is available on the VPS." >&2
    return 1
  fi
  echo "Rolling Ithute production back to last-known-good image $ROLLBACK_TAG." >&2
  images_present "$ROLLBACK_TAG" || return 1

  if [ -s "$LAST_GOOD_RUNTIME_ARCHIVE" ]; then
    tar -xzf "$LAST_GOOD_RUNTIME_ARCHIVE" -C "$APP_DIR" || return 1
  fi

  umask 077
  printf 'ITHUTE_IMAGE_TAG=%s\n' "$ROLLBACK_TAG" > "$ROLLBACK_IMAGE_ENV_FILE"
  chmod 600 "$ROLLBACK_IMAGE_ENV_FILE"
  ACTIVE_IMAGE_ENV_FILE="$ROLLBACK_IMAGE_ENV_FILE"
  validate_runtime || return 1

  # Never use --remove-orphans here or in the normal deployment path. Backup,
  # telemetry and restore-drill containers share the project intentionally and
  # must not be stopped merely because they live in auxiliary Compose files.
  compose up -d --no-build || {
    compose ps >&2 || true
    compose logs --tail=220 ithute-auth ithute-app-api ithute-web ithute-push ithute-realtime >&2 || true
    return 1
  }
  ensure_edge_and_reload || return 1
  verify_core_health || return 1
  verify_edge_private_network || return 1
  verify_public_health || return 1

  mv "$ROLLBACK_IMAGE_ENV_FILE" "$IMAGE_ENV_FILE"
  chmod 600 "$IMAGE_ENV_FILE"
  ACTIVE_IMAGE_ENV_FILE="$IMAGE_ENV_FILE"
  record_last_good "$ROLLBACK_TAG"
  echo "Rollback completed; production is healthy on $ROLLBACK_TAG." >&2
  return 0
}

fail_release() {
  dump_failure_logs
  if rollback_to_last_good; then
    echo "The candidate deployment failed, but the previous healthy production release was restored." >&2
  else
    echo "CRITICAL: candidate deployment failed and automated rollback could not restore service." >&2
  fi
  rm -f "$CANDIDATE_IMAGE_ENV_FILE" "$ROLLBACK_IMAGE_ENV_FILE"
  exit 1
}

validate_runtime || exit 1

# Pull only third-party runtime images. All Ithute application images were
# already built and tested by GitHub Actions. This happens before any live
# application container is replaced.
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

# Replace only services declared by the production Compose file. In particular,
# do not use --remove-orphans: operational services in the same project are not
# disposable just because they are described in telemetry/backup Compose files.
if ! compose up -d --no-build; then
  fail_release
fi
if ! ensure_edge_and_reload; then
  fail_release
fi
if ! verify_core_health; then
  fail_release
fi
if ! verify_edge_private_network; then
  echo "Managed private-network edge readiness failed after deployment." >&2
  fail_release
fi

# Peer reconciliation can only succeed after the public API name is reachable.
# The timer remains active either way and will retry automatically.
if getent ahostsv4 ithute.co.ls 2>/dev/null | awk '{print $1}' | grep -Fxq "$(sed -n 's/^ITHUTE_PUBLIC_IPV4=//p' "$ENV_FILE" | tail -n1)"; then
  systemctl start ithute-wireguard-edge-reconciler.service || {
    systemctl status --no-pager ithute-wireguard-edge-reconciler.service >&2 || true
    fail_release
  }
fi

if ! verify_public_health; then
  echo "Candidate failed public health verification." >&2
  fail_release
fi

# Commit the release marker only after the complete candidate is healthy. Until
# this point the previous .image.env and last-known-good marker remain intact.
mv "$CANDIDATE_IMAGE_ENV_FILE" "$IMAGE_ENV_FILE"
chmod 600 "$IMAGE_ENV_FILE"
ACTIVE_IMAGE_ENV_FILE="$IMAGE_ENV_FILE"
record_last_good "$CANDIDATE_TAG"
rm -f "$ROLLBACK_IMAGE_ENV_FILE"

compose ps
compose images
printf '\nIthute production is healthy. Last-known-good release: %s\n' "$CANDIDATE_TAG"
