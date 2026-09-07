#!/usr/bin/env sh
set -eu

: "${APP_DIR:?APP_DIR is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${TUTOR_HOST:?TUTOR_HOST is required}"
: "${VPS_HOST:?VPS_HOST is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"

sync_script="${TUTOR_SYNC_SCRIPT:-/tmp/ithute-tutor-sync-env-${DEPLOY_SHA}.py}"
image_bundle="/tmp/ithute-tutor-images-${DEPLOY_SHA}.tar.gz"
base_manifest="/tmp/docker-compose.ithute-tutor-${DEPLOY_SHA}.yml"
prod_manifest="/tmp/docker-compose.ithute-tutor-prod-${DEPLOY_SHA}.yml"

cleanup_staged() {
  rm -f "$sync_script" "$base_manifest" "$prod_manifest"
}
trap cleanup_staged EXIT HUP INT TERM

if command -v flock >/dev/null 2>&1; then
  exec 9>/tmp/ithute-production.lock
  lock_attempt=1
  while ! flock -n 9; do
    if [ "$lock_attempt" -ge 120 ]; then
      echo "Timed out waiting for the shared Ithute production lock." >&2
      exit 1
    fi
    echo "Waiting for shared Ithute production lock (attempt $lock_attempt/120)..."
    sleep 10
    lock_attempt=$((lock_attempt + 1))
  done
  echo "Acquired shared Ithute production lock for Tutor deployment."
fi

[ -s "$image_bundle" ] || {
  echo "Exact Tutor image bundle is missing: $image_bundle" >&2
  exit 1
}
[ -s "$base_manifest" ] || {
  echo "Tutor base manifest is missing: $base_manifest" >&2
  exit 1
}
[ -s "$prod_manifest" ] || {
  echo "Tutor production manifest is missing: $prod_manifest" >&2
  exit 1
}
[ -s "$sync_script" ] || {
  echo "Tutor environment reconciler is missing: $sync_script" >&2
  exit 1
}

python3 -m py_compile "$sync_script"

echo "Loading exact Tutor ${DEPLOY_SHA} images delivered by the trusted build runner."
gzip -dc "$image_bundle" | docker load
rm -f "$image_bundle"
docker image inspect "${BACKEND_IMAGE}:${DEPLOY_SHA}" >/dev/null
docker image inspect "${FRONTEND_IMAGE}:${DEPLOY_SHA}" >/dev/null

cd "$APP_DIR"
[ -f .env ] || { echo "Ithute production .env is missing" >&2; exit 1; }
cp "$base_manifest" docker-compose.ithute-tutor.yml
cp "$prod_manifest" docker-compose.ithute-tutor-prod.yml
chmod 600 .env

# Reconcile only Tutor's product settings and central identity registration.
CENTRAL_CHANGED="$(DEPLOY_SHA="$DEPLOY_SHA" ITHUTE_ENV_FILE=.env python3 "$sync_script")"
chmod 600 .env

# This workflow intentionally ignores unrelated containers in the existing
# mailbox-dns project. Never use --remove-orphans here: Tutor deployment must
# not stop or delete Pay, Mailbox, LoanHub, or any sibling product containers.
export COMPOSE_IGNORE_ORPHANS=true
COMPOSE_PROJECT_NAME_VALUE="${COMPOSE_PROJECT_NAME:-mailbox-dns}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ithute-platform.yml -f docker-compose.ithute-tutor.yml -f docker-compose.ithute-tutor-prod.yml -f docker-compose.deploy.yml"

compose() {
  docker compose -p "$COMPOSE_PROJECT_NAME_VALUE" $COMPOSE_FILES "$@"
}

service_status() {
  service="$1"
  id="$(compose ps -q "$service" 2>/dev/null || true)"
  if [ -z "$id" ]; then
    printf '%s\n' "not-started|"
    return 0
  fi
  docker inspect -f '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$id" 2>/dev/null || printf '%s\n' "unknown|"
}

wait_service() {
  service="$1"
  attempts="${2:-90}"
  n=1
  while [ "$n" -le "$attempts" ]; do
    state="$(service_status "$service")"
    runtime="${state%%|*}"
    health="${state#*|}"

    if [ -n "$health" ]; then
      case "$health" in
        healthy) echo "$service is healthy."; return 0 ;;
        unhealthy)
          echo "$service became unhealthy." >&2
          compose logs --tail=250 "$service" || true
          return 1
          ;;
      esac
    else
      case "$runtime" in
        running) echo "$service is running."; return 0 ;;
        exited|dead)
          echo "$service stopped with runtime state $runtime." >&2
          compose logs --tail=250 "$service" || true
          return 1
          ;;
      esac
    fi

    if [ $((n % 10)) -eq 0 ]; then
      echo "Waiting for $service (runtime: $runtime, health: ${health:-none}, attempt $n/$attempts)..."
    fi
    sleep 2
    n=$((n + 1))
  done

  echo "Timed out waiting for $service." >&2
  compose ps "$service" || true
  compose logs --tail=250 "$service" || true
  return 1
}

compose config >/dev/null

# Central Auth/Push are refreshed only when Tutor's own registration changed.
# On normal Tutor releases this block is skipped completely.
if [ "$CENTRAL_CHANGED" = "true" ]; then
  echo "Tutor identity registration changed; refreshing the central services required by Tutor."
  compose up -d --no-build --no-deps --force-recreate ithute-auth ithute-push ithute-push-worker
  wait_service ithute-auth 90
  wait_service ithute-push 90
  wait_service ithute-push-worker 90
fi

# From this point onward, only Tutor containers are recreated.
compose up -d --no-build --no-deps tutor-db
wait_service tutor-db 60

mkdir -p backups
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
tutor_backup="backups/ithute-tutor-before-${timestamp}.dump"
# Read PostgreSQL identity from the running Tutor database container so custom
# production DB/user values cannot make the pre-release backup target the wrong
# role or database.
compose exec -T tutor-db sh -c \
  'exec pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$tutor_backup"
test -s "$tutor_backup"
echo "Tutor database backup created: $tutor_backup"

compose up -d --no-build --no-deps --force-recreate tutor-backend
wait_service tutor-backend 120
compose exec -T tutor-backend curl -fsS http://127.0.0.1:8000/readyz >/dev/null

compose up -d --no-build --no-deps --force-recreate tutor-frontend
wait_service tutor-frontend 120

# Verify the existing internal reverse-proxy route without recreating nginx.
compose exec -T nginx wget -qO- --header='Host: tutor.ithute.co.ls' http://127.0.0.1/ >/dev/null

# Register only Tutor's authoritative DNS record through the existing DNS API.
compose exec -T backend python -m app.product_dns \
  --zone ithute.co.ls \
  --host "$TUTOR_HOST"

echo "Ithute Tutor deployment completed without mutating sibling product containers or the shared TLS edge."
