#!/usr/bin/env sh
set -eu

[ -f .env ] || { echo "Missing production .env in $(pwd)" >&2; exit 1; }
: "${MAILBOX_DNS_IMAGE_TAG:?MAILBOX_DNS_IMAGE_TAG is required}"

env_value() {
  key="$1"
  awk -F= -v k="$key" '$1 == k { sub(/^[^=]*=/, ""); print; exit }' .env
}

upsert_env() {
  key="$1"
  value="$2"
  tmp="$(mktemp)"
  awk -v k="$key" 'index($0, k "=") != 1 { print }' .env > "$tmp"
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
  chmod 600 .env
}

ensure_random_hex() {
  key="$1"
  value="$(env_value "$key")"
  case "$value" in
    ""|*replace-with*|*replace-this*|*ChangeMe*|*changeme*) upsert_env "$key" "$(openssl rand -hex 32)" ;;
  esac
}

ensure_csv_entry() {
  key="$1"
  entry="$2"
  value="$(env_value "$key")"
  case ",$value," in
    *",$entry,"*) return 0 ;;
  esac
  if [ -n "$value" ]; then value="$value,$entry"; else value="$entry"; fi
  upsert_env "$key" "$value"
}

repair_fernet_key() {
  key="$1"
  label="$2"
  current="$(env_value "$key")"

  if printf '%s\n' "$current" | grep -Eq '^[A-Za-z0-9_-]{43}=$'; then
    return 0
  fi

  replacement="$(openssl rand 32 | openssl base64 -A | tr '+/' '-_')"
  if ! printf '%s\n' "$replacement" | grep -Eq '^[A-Za-z0-9_-]{43}=$'; then
    echo "Failed to generate a valid Fernet key for $label" >&2
    exit 1
  fi

  upsert_env "$key" "$replacement"
  echo "Provisioned a valid persistent Fernet key for $label before production preflight."
}

provision_realtime_identity() {
  ensure_random_hex ITHUTE_REALTIME_DB_PASSWORD
  ensure_random_hex ITHUTE_SERVICE_REALTIME_SECRET
  ensure_csv_entry ITHUTE_AUTH_FIRST_PARTY_CLIENTS 'ithute-realtime:!thute Realtime'
  ensure_csv_entry ITHUTE_PUSH_ALLOWED_SERVICE_CLIENTS 'ithute-realtime'
  ensure_csv_entry ITHUTE_PUSH_DELEGATED_SERVICE_CLIENTS 'ithute-realtime'

  realtime_secret="$(env_value ITHUTE_SERVICE_REALTIME_SECRET)"
  service_map="$(env_value ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON)"
  case "$service_map" in
    ""|'{}')
      service_map="{\"ithute-realtime\":\"${realtime_secret}\"}"
      ;;
    *'"ithute-realtime"'*)
      :
      ;;
    \{*\})
      service_map="${service_map%?},\"ithute-realtime\":\"${realtime_secret}\"}"
      ;;
    *)
      echo "Invalid ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON; refusing to overwrite it" >&2
      exit 1
      ;;
  esac
  upsert_env ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON "$service_map"
}

# Preserve valid encryption material and generate missing keys only once in the
# VPS-owned .env. Rotating either Fernet key implicitly would make encrypted
# Auth MFA or Push endpoint data unreadable, so valid existing values are kept.
repair_fernet_key ITHUTE_AUTH_TOTP_ENCRYPTION_KEY '!thute Auth MFA'
repair_fernet_key ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY '!thute Push endpoints'
provision_realtime_identity

. scripts/load-dotenv.sh
load_dotenv .env

sh scripts/prod-preflight.sh

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml -f docker-compose.phase12-monitoring.yml -f docker-compose.ithute-platform.yml"

# On a dedicated Mailbox-DNS host the commercial production overlay owns the
# public HTTP/HTTPS edge through Caddy. On a shared VPS another stack may
# already own 80/443; in that case Nginx remains the Mailbox-DNS upstream and
# the existing host reverse proxy forwards traffic to PROXY_PORT instead.
if [ "${SHARED_HTTP_EDGE:-false}" = "true" ]; then
  echo "Shared HTTP edge enabled; Mailbox-DNS Caddy will not be started."
else
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.commercial-prod.yml"
fi

COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.deploy.yml"
if [ "${HA_MAIL_ENABLED:-false}" = "true" ]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.ha-mail.yml -f docker-compose.deploy-ha.yml"
fi

compose() {
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES "$@"
}

retry() {
  attempts="$1"
  shift
  n=1
  while ! "$@"; do
    if [ "$n" -ge "$attempts" ]; then
      return 1
    fi
    echo "Command failed (attempt $n/$attempts); retrying in 10 seconds..." >&2
    n=$((n + 1))
    sleep 10
  done
}

wait_service() {
  service="$1"
  max_attempts="${2:-60}"
  id="$(compose ps -q "$service")"
  [ -n "$id" ] || { echo "Service $service has no container" >&2; return 1; }
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || true)"
    case "$status" in
      healthy|running) return 0 ;;
      exited|dead|unhealthy)
        echo "Service $service entered $status" >&2
        compose logs --tail=200 "$service" || true
        docker inspect -f '{{json .State}}' "$id" 2>/dev/null || true
        return 1
        ;;
    esac
    sleep 2
    attempt=$((attempt + 1))
  done
  echo "Timed out waiting for $service" >&2
  compose logs --tail=200 "$service" || true
  docker inspect -f '{{json .State}}' "$id" 2>/dev/null || true
  return 1
}

frontend_probe() {
  compose exec -T frontend node -e "const http=require('http');const req=http.get('http://127.0.0.1:3000/',res=>{res.resume();process.exit(res.statusCode>=200&&res.statusCode<400?0:1)});req.setTimeout(4000,()=>{req.destroy();process.exit(1)});req.on('error',()=>process.exit(1));"
}

startup_diagnostics() {
  echo "=== Production startup diagnostics ===" >&2
  compose ps >&2 || true
  for service in frontend backend nginx ithute-auth ithute-push ithute-push-worker ithute-realtime ithute-realtime-db ithute-realtime-redis; do
    id="$(compose ps -q "$service" 2>/dev/null || true)"
    if [ -n "$id" ]; then
      echo "--- $service state ---" >&2
      docker inspect -f '{{json .State}}' "$id" >&2 2>/dev/null || true
      echo "--- $service logs ---" >&2
      compose logs --tail=300 "$service" >&2 2>/dev/null || true
    fi
  done
}

mkdir -p backups platform-secrets/ithute-auth platform-secrets/ithute-push
chmod 700 platform-secrets platform-secrets/ithute-auth platform-secrets/ithute-push
compose config >/dev/null
# All immutable production images are published for the same release SHA by the
# production build job. Retry pulls briefly to tolerate registry propagation.
retry 24 compose pull

# Bring persistent data services up first so a pre-release backup can be taken
# before any application applies Alembic migrations.
compose up -d --no-build --pull never postgres redis powerdns-db rspamd-redis restore-postgres ithute-auth-db ithute-push-db ithute-realtime-db ithute-realtime-redis
wait_service postgres 60
wait_service redis 60
wait_service powerdns-db 60
wait_service rspamd-redis 60
wait_service ithute-auth-db 60
wait_service ithute-push-db 60
wait_service ithute-realtime-db 60
wait_service ithute-realtime-redis 60

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
app_backup="backups/app-before-${timestamp}.dump"
pdns_backup="backups/powerdns-before-${timestamp}.dump"
auth_backup="backups/ithute-auth-before-${timestamp}.dump"
push_backup="backups/ithute-push-before-${timestamp}.dump"
realtime_backup="backups/ithute-realtime-before-${timestamp}.dump"

echo "Creating pre-release application database backup: $app_backup"
compose exec -T postgres pg_dump --format=custom --no-owner --no-privileges -U "${POSTGRES_USER:-lelefamail}" "${POSTGRES_DB:-lelefamail}" > "$app_backup"
test -s "$app_backup"

echo "Creating pre-release PowerDNS database backup: $pdns_backup"
compose exec -T powerdns-db pg_dump --format=custom --no-owner --no-privileges -U "${POWERDNS_DB_USER:-powerdns}" "${POWERDNS_DB_NAME:-powerdns}" > "$pdns_backup"
test -s "$pdns_backup"

echo "Creating pre-release !thute Auth database backup: $auth_backup"
compose exec -T ithute-auth-db pg_dump --format=custom --no-owner --no-privileges -U "${ITHUTE_AUTH_DB_USER:-ithute_auth}" "${ITHUTE_AUTH_DB_NAME:-ithute_auth}" > "$auth_backup"
test -s "$auth_backup"

echo "Creating pre-release !thute Push database backup: $push_backup"
compose exec -T ithute-push-db pg_dump --format=custom --no-owner --no-privileges -U "${ITHUTE_PUSH_DB_USER:-ithute_push}" "${ITHUTE_PUSH_DB_NAME:-ithute_push}" > "$push_backup"
test -s "$push_backup"

echo "Creating pre-release !thute Realtime database backup: $realtime_backup"
compose exec -T ithute-realtime-db pg_dump --format=custom --no-owner --no-privileges -U "${ITHUTE_REALTIME_DB_USER:-ithute_realtime}" "${ITHUTE_REALTIME_DB_NAME:-ithute_realtime}" > "$realtime_backup"
test -s "$realtime_backup"

# The production backend and central platform API commands apply their own
# Alembic migrations. If Compose stops because a dependency is unhealthy,
# capture the exact container state/logs.
if ! compose up -d --no-build --pull never --remove-orphans; then
  startup_diagnostics
  exit 1
fi
wait_service backend 90
wait_service ithute-auth 90
wait_service ithute-push 90
wait_service ithute-push-worker 90
wait_service ithute-realtime 90

# Keep the configured bootstrap account authoritative for platform-owner login.
# The password is read only from the production environment and is never stored
# in source control or printed to deployment logs.
compose exec -T backend python - <<'PY'
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User

with SessionLocal() as db:
    email = settings.bootstrap_admin_email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(settings.bootstrap_admin_password),
            full_name="Platform Owner",
            is_platform_owner=True,
            is_active=True,
        )
        db.add(user)
    else:
        user.password_hash = hash_password(settings.bootstrap_admin_password)
        user.is_platform_owner = True
        user.is_active = True
    db.commit()
print("Bootstrap platform owner synchronized")
PY

# A mail-enabled domain on platform-hosted authoritative DNS must not require a
# production shell intervention to become deliverable. Reconcile all existing
# verified domains on every release. The operation is idempotent: existing DKIM
# identities are reused and unrelated apex TXT records are preserved.
echo "Reconciling managed mail DNS and DKIM signing identities..."
compose exec -T backend python -m app.services.mail_dns_reconcile_cli

# Nginx resolves Docker service names when its worker starts. A normal Compose
# update can recreate upstreams while leaving an unchanged Nginx container
# running with stale container IPs. Recreate it on every release after all
# application services are healthy.
wait_service frontend 90
compose up -d --no-deps --force-recreate nginx
wait_service nginx 90

for service in powerdns dovecot postfix rspamd smtp-policy radicale backup-scheduler backup-recovery prometheus grafana; do
  wait_service "$service" 90
done

if [ "${SHARED_HTTP_EDGE:-false}" != "true" ]; then
  wait_service caddy 90
fi

# Verify readiness inside the Docker network before relying on public DNS/TLS.
compose exec -T backend curl -fsS http://127.0.0.1:8000/health/ready >/dev/null
frontend_probe >/dev/null
compose exec -T ithute-auth curl -fsS http://127.0.0.1:8080/healthz >/dev/null
compose exec -T ithute-push curl -fsS http://127.0.0.1:8080/healthz >/dev/null
compose exec -T ithute-realtime curl -fsS http://127.0.0.1:8080/readyz >/dev/null
compose exec -T nginx wget -qO- http://127.0.0.1/ >/dev/null
compose exec -T nginx wget -qO- --header='Host: auth.ithute.co.ls' http://127.0.0.1/healthz | grep -q 'ithute-auth'
compose exec -T nginx wget -qO- --header='Host: push.ithute.co.ls' http://127.0.0.1/healthz | grep -q 'ithute-push'
compose exec -T nginx wget -qO- --header='Host: realtime.ithute.co.ls' http://127.0.0.1/healthz | grep -q 'ithute-realtime'

if grep -q '^MAILBOX_DNS_IMAGE_TAG=' .env; then
  sed -i "s/^MAILBOX_DNS_IMAGE_TAG=.*/MAILBOX_DNS_IMAGE_TAG=${MAILBOX_DNS_IMAGE_TAG}/" .env
else
  printf '\nMAILBOX_DNS_IMAGE_TAG=%s\n' "$MAILBOX_DNS_IMAGE_TAG" >> .env
fi

printf '\nMailbox DNS + Ithute platform production deployment completed.\n'
printf 'Image tag: %s\n' "$MAILBOX_DNS_IMAGE_TAG"
printf '!thute Auth: healthy on internal service ithute-auth:8080\n'
printf '!thute Push: healthy on internal service ithute-push:8080\n'
printf '!thute Realtime: healthy on internal service ithute-realtime:8080\n'
if [ "${SHARED_HTTP_EDGE:-false}" = "true" ]; then
  case "${PROXY_PORT:-8086}" in
    *:*) proxy_target="${PROXY_PORT}" ;;
    *) proxy_target="127.0.0.1:${PROXY_PORT:-8086}" ;;
  esac
  printf 'HTTP upstream for existing reverse proxy: http://%s\n' "$proxy_target"
  printf 'LoanHub/existing host edge remains responsible for public 80/443.\n'
else
  printf 'Panel:     https://%s\n' "$PANEL_HOSTNAME"
  printf 'API:       https://%s\n' "$API_HOSTNAME"
  printf 'Groupware: https://%s\n' "$GROUPWARE_HOSTNAME"
  printf 'Realtime:  https://realtime.ithute.co.ls\n'
fi
compose ps

docker image prune -f >/dev/null 2>&1 || true
