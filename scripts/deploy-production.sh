#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
ENV_FILE="${ITHUTE_ENV_FILE:-$APP_DIR/.env.production}"
IMAGE_ENV_FILE="${ITHUTE_IMAGE_ENV_FILE:-$APP_DIR/.image.env}"
COMPOSE_FILE="$APP_DIR/compose.production.yml"
PROJECT_NAME="ithute"

cd "$APP_DIR"

test -f "$ENV_FILE" || { echo "Missing $ENV_FILE. Run the safe bootstrap once first." >&2; exit 2; }
test -f "$COMPOSE_FILE" || { echo "Missing $COMPOSE_FILE" >&2; exit 2; }
test -f "$APP_DIR/infrastructure/caddy/Caddyfile" || { echo "Missing Caddyfile" >&2; exit 2; }
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
if ! grep -Fq "ghcr.io/ithute-stak/ithute-web:" /tmp/ithute-compose.rendered.yml; then
  echo "Refusing deployment: Ithute web image is not sourced from GHCR." >&2
  exit 1
fi

# Images are built and published by GitHub Actions. The VPS only pulls and runs
# the immutable commit-tagged images; it never builds application source.
compose pull
compose up -d --remove-orphans --no-build

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
compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null

if [ "${ITHUTE_REQUIRE_PUBLIC_HEALTH:-0}" = "1" ]; then
  html="$(curl --retry 15 --retry-delay 3 --retry-all-errors -fsS https://ithute.co.ls/)"
  printf '%s' "$html" | grep -Fq 'One focused platform.'
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://auth.ithute.co.ls/healthz | grep -q ithute-auth
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://push.ithute.co.ls/readyz | grep -q '"status":"ready"'
  curl --retry 10 --retry-delay 2 --retry-all-errors -fsS https://realtime.ithute.co.ls/readyz | grep -q '"status":"ready"'
fi

compose ps
compose images
printf '\nIthute immutable-image deployment is healthy.\n'
