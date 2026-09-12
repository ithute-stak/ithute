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
test -f "$APP_DIR/infrastructure/dns/named.conf" || { echo "Missing authoritative DNS config" >&2; exit 2; }
test -f "$APP_DIR/infrastructure/dns/zones/db.ithute.co.ls" || { echo "Missing Ithute DNS zone" >&2; exit 2; }
test -f "$APP_DIR/secrets/ithute-auth/jwt-private.pem" || { echo "Missing Auth private key" >&2; exit 2; }
test -f "$APP_DIR/secrets/ithute-auth/jwt-public.pem" || { echo "Missing Auth public key" >&2; exit 2; }

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

# Only third-party base images are pulled on the VPS. Ithute application images
# were already built in GitHub Actions and loaded from the deployment artifact.
compose pull ithute-auth-db ithute-push-db ithute-realtime-db ithute-realtime-redis ithute-dns caddy
compose up -d --remove-orphans --no-build

# Compose does not recreate a running service merely because a bind-mounted
# configuration file changed. Explicitly activate the newly uploaded runtime
# configuration so verification checks the configuration from this deployment,
# not whatever Caddy/BIND had already loaded in memory.
compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null
compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null
if ! compose exec -T ithute-dns rndc reload >/dev/null 2>&1; then
  compose restart ithute-dns >/dev/null
fi

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

check_service ithute-web "wget -qO- http://127.0.0.1:3000/health | grep -q ithute-web"
check_service ithute-auth "curl -fsS http://127.0.0.1:8080/healthz | grep -q ithute-auth"
check_service ithute-push "curl -fsS http://127.0.0.1:8080/readyz | grep -q '\"status\":\"ready\"'"
check_service ithute-realtime "curl -fsS http://127.0.0.1:8080/readyz | grep -q '\"status\":\"ready\"'"
check_service ithute-dns "named-checkconf /etc/bind/named.conf && named-checkzone ithute.co.ls /etc/bind/zones/db.ithute.co.ls >/dev/null"

if [ "${ITHUTE_REQUIRE_PUBLIC_HEALTH:-0}" = "1" ]; then
  html="$(curl --retry 15 --retry-delay 3 --retry-all-errors -fsS https://ithute.co.ls/)"
  printf '%s' "$html" | grep -Fq 'One focused platform.'
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://auth.ithute.co.ls/healthz | grep -q ithute-auth
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://push.ithute.co.ls/readyz | grep -q '"status":"ready"'
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://realtime.ithute.co.ls/readyz | grep -q '"status":"ready"'
fi

compose ps
compose images
printf '\nIthute immutable-image deployment and authoritative DNS are healthy.\n'
