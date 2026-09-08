#!/usr/bin/env sh
set -eu

: "${APP_DIR:?APP_DIR is required}"
: "${EDGE_DIR:?EDGE_DIR is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${PRODUCT_HOST:?PRODUCT_HOST is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${OWNER_FILE:?OWNER_FILE is required}"

image_bundle="/tmp/buildtrack-images-${DEPLOY_SHA}.tar.gz"
manifest="/tmp/docker-compose.buildtrack-${DEPLOY_SHA}.yml"
sync_script="/tmp/buildtrack-sync-env-${DEPLOY_SHA}.py"
edge_template="/tmp/buildtrack-edge-${DEPLOY_SHA}.conf.template"

cleanup() {
  rm -f "$manifest" "$sync_script" "$edge_template" "$OWNER_FILE"
}
trap cleanup EXIT HUP INT TERM

if command -v flock >/dev/null 2>&1; then
  exec 9>/tmp/ithute-production.lock
  attempt=1
  while ! flock -n 9; do
    if [ "$attempt" -ge 120 ]; then
      echo "Timed out waiting for the shared Ithute production lock." >&2
      exit 1
    fi
    sleep 10
    attempt=$((attempt + 1))
  done
fi

for file in "$image_bundle" "$manifest" "$sync_script" "$edge_template" "$OWNER_FILE"; do
  [ -s "$file" ] || { echo "Required staged deployment file is missing: $file" >&2; exit 1; }
done
chmod 600 "$OWNER_FILE"
python3 -m py_compile "$sync_script"

echo "Loading exact BuildTrack images for ${DEPLOY_SHA}."
gzip -dc "$image_bundle" | docker load
rm -f "$image_bundle"
docker image inspect "${BACKEND_IMAGE}:${DEPLOY_SHA}" >/dev/null
docker image inspect "${FRONTEND_IMAGE}:${DEPLOY_SHA}" >/dev/null

cd "$APP_DIR"
[ -f .env ] || { echo "Ithute production .env is missing" >&2; exit 1; }
cp "$manifest" docker-compose.buildtrack.yml
chmod 600 .env
CENTRAL_CHANGED="$(DEPLOY_SHA="$DEPLOY_SHA" ITHUTE_ENV_FILE=.env python3 "$sync_script")"
chmod 600 .env

export COMPOSE_IGNORE_ORPHANS=true
COMPOSE_PROJECT_NAME_VALUE="${COMPOSE_PROJECT_NAME:-mailbox-dns}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ithute-platform.yml -f docker-compose.buildtrack.yml -f docker-compose.deploy.yml"

compose() {
  docker compose -p "$COMPOSE_PROJECT_NAME_VALUE" $COMPOSE_FILES "$@"
}

service_state() {
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
    state="$(service_state "$service")"
    runtime="${state%%|*}"
    health="${state#*|}"
    if [ -n "$health" ]; then
      case "$health" in
        healthy) echo "$service is healthy."; return 0 ;;
        unhealthy)
          compose logs --tail=250 "$service" || true
          return 1
          ;;
      esac
    else
      case "$runtime" in
        running) echo "$service is running."; return 0 ;;
        exited|dead)
          compose logs --tail=250 "$service" || true
          return 1
          ;;
      esac
    fi
    sleep 2
    n=$((n + 1))
  done
  compose logs --tail=250 "$service" || true
  echo "Timed out waiting for $service." >&2
  return 1
}

run_oneshot() {
  service="$1"
  compose rm -sf "$service" >/dev/null 2>&1 || true
  compose up --no-build --no-deps --abort-on-container-exit --exit-code-from "$service" "$service"
}

compose config >/dev/null

# Refresh only shared services whose registration changed. Sibling product
# containers are never removed or recreated by this deployment.
if [ "$CENTRAL_CHANGED" = "true" ]; then
  compose up -d --no-build --no-deps --force-recreate ithute-auth ithute-push ithute-push-worker ithute-realtime
  wait_service ithute-auth 90
  wait_service ithute-push 90
  wait_service ithute-push-worker 90
  wait_service ithute-realtime 90
fi

# Provision/update the requested central Ithute identity from a protected
# runtime secret. The plaintext never enters Git, the shared .env, or logs.
owner_email="$(sed -n '1p' "$OWNER_FILE")"
owner_password="$(sed -n '2p' "$OWNER_FILE")"
[ "$owner_email" = "justy@ithute.co.ls" ] || { echo "Unexpected BuildTrack owner email" >&2; exit 1; }
[ -n "$owner_password" ] || { echo "BuildTrack owner password secret is empty" >&2; exit 1; }

compose exec -T \
  -e BUILDTRACK_OWNER_EMAIL="$owner_email" \
  -e BUILDTRACK_OWNER_PASSWORD="$owner_password" \
  ithute-auth python - <<'PY'
import os
from sqlalchemy import select
from app.db import SessionLocal
from app.models import AuthSession, User, utcnow
from app.security import hash_password, normalize_email
from app.security_service import record_audit

email = normalize_email(os.environ["BUILDTRACK_OWNER_EMAIL"])
password = os.environ["BUILDTRACK_OWNER_PASSWORD"]
if not email or not password:
    raise SystemExit("owner identity material is incomplete")

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            display_name="Nthane Brothers Super Administrator",
            password_hash=hash_password(password),
            is_active=True,
            email_verified=True,
        )
        db.add(user)
        db.flush()
        event_type = "buildtrack_superadmin_created"
    else:
        user.password_hash = hash_password(password)
        user.is_active = True
        user.email_verified = True
        user.failed_login_attempts = 0
        user.locked_until = None
        user.password_changed_at = utcnow()
        user.security_version = int(user.security_version or 0) + 1
        sessions = db.scalars(
            select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        ).all()
        for session in sessions:
            session.revoked_at = utcnow()
            session.revoked_reason = "Nthane Brothers owner credential provisioned"
        event_type = "buildtrack_superadmin_updated"
    record_audit(
        db,
        event_type=event_type,
        user=user,
        client_id="buildtrack-construction",
        details={"product": "Nthane Brothers Construction Management System"},
    )
    db.commit()
    print(f"Central Ithute identity ready: {email}")
PY
unset owner_password
rm -f "$OWNER_FILE"

# Product-local state is isolated and backed up before schema/runtime changes.
compose up -d --no-build --no-deps buildtrack-db buildtrack-redis
wait_service buildtrack-db 60
wait_service buildtrack-redis 60
mkdir -p backups
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="backups/buildtrack-before-${timestamp}.dump"
compose exec -T buildtrack-db sh -c \
  'exec pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$backup"
test -s "$backup"
echo "BuildTrack database backup created: $backup"

run_oneshot buildtrack-migrate
run_oneshot buildtrack-bootstrap

compose up -d --no-build --no-deps --force-recreate buildtrack-backend
wait_service buildtrack-backend 120
compose exec -T buildtrack-backend python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/deployment', timeout=5)" >/dev/null

compose up -d --no-build --no-deps --force-recreate buildtrack-frontend
wait_service buildtrack-frontend 120

# Register only this product's authoritative DNS record.
compose exec -T backend python -m app.product_dns --zone ithute.co.ls --host "$PRODUCT_HOST"

# Expand the existing shared certificate before activating the new virtual host.
# The current SAN set is discovered from Certbot so no sibling hostname is lost.
cd "$EDGE_DIR"
edge() {
  docker compose -p ithute-edge -f docker-compose.ithute-edge.yml "$@"
}

current_domains="$(edge run --rm --no-deps --entrypoint certbot certbot certificates --cert-name ithute-edge 2>/dev/null | sed -n 's/^[[:space:]]*Domains: //p' | tail -n1)"
[ -n "$current_domains" ] || { echo "Could not discover the shared ithute-edge certificate SANs" >&2; exit 1; }
case " $current_domains " in
  *" $PRODUCT_HOST "*) : ;;
  *)
    # Give authoritative DNS a short propagation window before ACME validation.
    sleep 15
    set -- certonly --webroot -w /var/www/certbot --cert-name ithute-edge --expand --non-interactive --agree-tos
    for domain in $current_domains "$PRODUCT_HOST"; do
      set -- "$@" -d "$domain"
    done
    edge run --rm --no-deps --entrypoint certbot certbot "$@"
    ;;
esac

cp "$edge_template" infrastructure/ithute-edge/default.conf.template
edge run --rm --no-deps --entrypoint /bin/sh edge-nginx -c \
  '/docker-entrypoint.d/20-envsubst-on-templates.sh >/dev/null && nginx -t' >/dev/null
edge up -d --no-build --no-deps --force-recreate edge-nginx certbot

edge_id="$(edge ps -q edge-nginx)"
[ -n "$edge_id" ] || { echo "Shared edge did not start" >&2; exit 1; }
n=1
while [ "$n" -le 45 ]; do
  if edge exec -T edge-nginx nginx -T 2>/dev/null | grep -Fq 'server_name nbro.ithute.co.ls;'; then
    break
  fi
  sleep 2
  n=$((n + 1))
done
[ "$n" -le 45 ] || { edge logs --tail=250 edge-nginx >&2 || true; exit 1; }
edge exec -T edge-nginx nginx -t >/dev/null

# Verify the product through the same public HTTPS route users will use.
healthy=false
for attempt in $(seq 1 20); do
  if curl -fsS --connect-timeout 5 --max-time 20 "https://${PRODUCT_HOST}/health/deployment" >/dev/null \
    && curl -fsS --connect-timeout 5 --max-time 20 "https://${PRODUCT_HOST}/index" >/dev/null; then
    healthy=true
    break
  fi
  sleep 5
done
[ "$healthy" = true ] || { echo "Public BuildTrack verification failed" >&2; exit 1; }

echo "Nthane Brothers BuildTrack deployment completed at https://${PRODUCT_HOST}."
