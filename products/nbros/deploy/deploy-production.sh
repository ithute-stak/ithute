#!/usr/bin/env sh
set -eu

: "${PLATFORM_ROOT:?PLATFORM_ROOT is required}"
: "${EDGE_DIR:?EDGE_DIR is required}"
: "${RUNTIME_DIR:?RUNTIME_DIR is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${PRODUCT_HOST:?PRODUCT_HOST is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${AUTH_IMAGE:?AUTH_IMAGE is required}"
: "${REALTIME_IMAGE:?REALTIME_IMAGE is required}"

BUNDLE="/tmp/nbros-images-${DEPLOY_SHA}.tar.gz"
STAGE="/tmp/nbros-release-${DEPLOY_SHA}"
EDGE_TEMPLATE="${STAGE}/edge-default.conf.template"

cleanup() {
  rm -rf "$STAGE" "$BUNDLE"
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

for file in "$BUNDLE" "$STAGE/compose.yaml" "$STAGE/compose.production.yml" "$EDGE_TEMPLATE"; do
  [ -s "$file" ] || { echo "Missing staged NBros release file: $file" >&2; exit 1; }
done

echo "Loading exact NBros and central platform images for ${DEPLOY_SHA}."
gzip -dc "$BUNDLE" | docker load
for image in "$BACKEND_IMAGE" "$FRONTEND_IMAGE" "$AUTH_IMAGE" "$REALTIME_IMAGE"; do
  docker image inspect "$image" >/dev/null
done

mkdir -p "$RUNTIME_DIR/backups"
chmod 700 "$RUNTIME_DIR"
cd "$RUNTIME_DIR"
cp "$STAGE/compose.yaml" compose.yaml
cp "$STAGE/compose.production.yml" compose.production.yml

if [ ! -s .env ]; then
  umask 077
  DB_PASSWORD="$(openssl rand -hex 32)"
  REALTIME_SECRET="$(openssl rand -hex 32)"
  cat > .env <<EOF
COMPOSE_PROJECT_NAME=nbros
NBROS_DB_NAME=nbros
NBROS_DB_USER=nbros
NBROS_DB_PASSWORD=${DB_PASSWORD}
NBROS_PUBLIC_URL=https://${PRODUCT_HOST}
NBROS_BACKEND_PORT=8203
NBROS_FRONTEND_PORT=3203
NBROS_AUTH_ISSUER=https://auth.ithute.co.ls
NBROS_AUTH_AUDIENCE=nbros
NBROS_AUTH_JWKS_URL=https://auth.ithute.co.ls/.well-known/jwks.json
NBROS_AUTH_SERVICE_TOKEN_URL=https://auth.ithute.co.ls/v1/auth/service-token
NBROS_BOOTSTRAP_ADMIN_EMAIL=justy@ithute.co.ls
NBROS_REALTIME_PUBLIC_URL=https://realtime.ithute.co.ls
NBROS_REALTIME_WS_URL=wss://realtime.ithute.co.ls/v1/ws
NBROS_REALTIME_SERVICE_CLIENT_SECRET=${REALTIME_SECRET}
NBROS_REALTIME_PUBLISH_ENABLED=true
NBROS_COOKIE_SECURE=true
NBROS_AI_ENABLED=false
ITHUTE_MAILBOX_NETWORK_NAME=mailbox-dns_mailbox_dns
EOF
fi
chmod 600 .env

# Ensure production values that must never drift are pinned while preserving
# generated passwords/secrets and any later operator configuration.
python3 - "$RUNTIME_DIR/.env" "$PRODUCT_HOST" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1]); host = sys.argv[2]
values = {}
order = []
for raw in path.read_text().splitlines():
    if not raw or raw.lstrip().startswith('#') or '=' not in raw:
        continue
    key, value = raw.split('=', 1)
    if key not in values: order.append(key)
    values[key] = value
required = {
    'COMPOSE_PROJECT_NAME': 'nbros',
    'NBROS_PUBLIC_URL': f'https://{host}',
    'NBROS_AUTH_ISSUER': 'https://auth.ithute.co.ls',
    'NBROS_AUTH_AUDIENCE': 'nbros',
    'NBROS_AUTH_JWKS_URL': 'https://auth.ithute.co.ls/.well-known/jwks.json',
    'NBROS_AUTH_SERVICE_TOKEN_URL': 'https://auth.ithute.co.ls/v1/auth/service-token',
    'NBROS_REALTIME_PUBLIC_URL': 'https://realtime.ithute.co.ls',
    'NBROS_REALTIME_WS_URL': 'wss://realtime.ithute.co.ls/v1/ws',
    'NBROS_COOKIE_SECURE': 'true',
    'ITHUTE_MAILBOX_NETWORK_NAME': 'mailbox-dns_mailbox_dns',
}
for key, value in required.items():
    if key not in values: order.append(key)
    values[key] = value
for key in ('NBROS_DB_PASSWORD', 'NBROS_REALTIME_SERVICE_CLIENT_SECRET'):
    if len(values.get(key, '')) < 24:
        raise SystemExit(f'{key} is missing or too short; refusing deployment')
path.write_text('\n'.join(f'{key}={values[key]}' for key in order) + '\n')
PY

# Read only the few runtime values this shell needs. Never source a Docker
# Compose .env file: valid Compose values can contain spaces, JSON, or other
# characters that are not safe POSIX shell syntax.
read_env_value() {
  env_file="$1"
  env_key="$2"
  python3 - "$env_file" "$env_key" <<'PY'
from pathlib import Path
import shlex
import sys

path = Path(sys.argv[1])
wanted = sys.argv[2]
for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
    if not raw or raw.lstrip().startswith('#') or '=' not in raw:
        continue
    key, value = raw.split('=', 1)
    if key.strip() != wanted:
        continue
    value = value.strip()
    if value:
        try:
            parsed = shlex.split(value, posix=True)
        except ValueError:
            parsed = []
        if len(parsed) == 1:
            value = parsed[0]
    print(value)
    break
PY
}

NBROS_REALTIME_SERVICE_CLIENT_SECRET="$(read_env_value "$RUNTIME_DIR/.env" NBROS_REALTIME_SERVICE_CLIENT_SECRET)"
NBROS_BACKEND_PORT="$(read_env_value "$RUNTIME_DIR/.env" NBROS_BACKEND_PORT)"
NBROS_FRONTEND_PORT="$(read_env_value "$RUNTIME_DIR/.env" NBROS_FRONTEND_PORT)"
NETWORK_NAME="$(read_env_value "$RUNTIME_DIR/.env" ITHUTE_MAILBOX_NETWORK_NAME)"
NETWORK_NAME="${NETWORK_NAME:-mailbox-dns_mailbox_dns}"

export NBROS_BACKEND_IMAGE="$BACKEND_IMAGE"
export NBROS_FRONTEND_IMAGE="$FRONTEND_IMAGE"
compose() {
  docker compose -p nbros --env-file .env -f compose.yaml -f compose.production.yml "$@"
}

compose config -q
docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 || {
  echo "Required shared Ithute network is missing: $NETWORK_NAME" >&2
  exit 1
}

# Preserve both business database and uploaded documents before changing the
# running release. First deployment legitimately has no existing volumes yet.
if docker volume inspect nbros_nbros_uploads >/dev/null 2>&1; then
  UPLOAD_BACKUP="$RUNTIME_DIR/backups/nbros-uploads-before-$(date -u +%Y%m%dT%H%M%SZ)-${DEPLOY_SHA}.tar.gz"
  docker run --rm -v nbros_nbros_uploads:/source:ro -v "$RUNTIME_DIR/backups:/backup" alpine:3.22 \
    sh -c "tar -C /source -czf /backup/$(basename "$UPLOAD_BACKUP") ."
  test -s "$UPLOAD_BACKUP"
  sha256sum "$UPLOAD_BACKUP" > "${UPLOAD_BACKUP}.sha256"
fi

compose up -d --no-build db redis
for service in db redis; do
  id="$(compose ps -q "$service")"
  [ -n "$id" ] || { echo "$service did not start" >&2; exit 1; }
  healthy=false
  for attempt in $(seq 1 60); do
    state="$(docker inspect "$id" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
    if [ "$state" = healthy ] || [ "$state" = running ]; then healthy=true; break; fi
    if [ "$state" = unhealthy ] || [ "$state" = exited ] || [ "$state" = dead ]; then break; fi
    sleep 2
  done
  [ "$healthy" = true ] || { compose logs --tail=200 "$service" >&2 || true; exit 1; }
done

DB_BACKUP="$RUNTIME_DIR/backups/nbros-before-$(date -u +%Y%m%dT%H%M%SZ)-${DEPLOY_SHA}.dump"
compose exec -T db sh -c 'exec pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$DB_BACKUP"
test -s "$DB_BACKUP"
sha256sum "$DB_BACKUP" > "${DB_BACKUP}.sha256"

# Provision NBros' service credential into Central Auth without replacing any
# sibling product registrations. The secret remains VPS-owned in .env files.
CENTRAL_ENV="$PLATFORM_ROOT/.env"
[ -s "$CENTRAL_ENV" ] || { echo "Central Ithute production .env is missing" >&2; exit 1; }
python3 - "$CENTRAL_ENV" "$NBROS_REALTIME_SERVICE_CLIENT_SECRET" <<'PY'
from pathlib import Path
import json, sys
path = Path(sys.argv[1]); secret = sys.argv[2]
lines = path.read_text().splitlines()
values = {}
for line in lines:
    if line and not line.lstrip().startswith('#') and '=' in line:
        key, value = line.split('=', 1); values[key] = value
raw = values.get('ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON', '{}') or '{}'
try: mapping = json.loads(raw)
except json.JSONDecodeError as exc: raise SystemExit(f'Invalid ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON: {exc}')
if not isinstance(mapping, dict): raise SystemExit('ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON is not an object')
mapping['nbros'] = secret
new_value = json.dumps(mapping, separators=(',', ':'))
out = []
written = False
for line in lines:
    if line.startswith('ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON='):
        out.append('ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON=' + new_value); written = True
    else: out.append(line)
if not written: out.append('ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON=' + new_value)
path.write_text('\n'.join(out) + '\n')
PY
chmod 600 "$CENTRAL_ENV"

# Refresh only Auth/Realtime components required by NBros. Existing databases,
# Push and sibling products are not recreated. The central .env is passed to
# Docker Compose as data and is never executed by this shell.
cd "$PLATFORM_ROOT"
CENTRAL_PROJECT="$(read_env_value "$CENTRAL_ENV" COMPOSE_PROJECT_NAME)"
CENTRAL_PROJECT="${CENTRAL_PROJECT:-mailbox-dns}"
CENTRAL_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ithute-platform.yml -f docker-compose.deploy.yml"
central() {
  ITHUTE_AUTH_IMAGE="ghcr.io/ithute-stak/ithute-auth" \
  ITHUTE_REALTIME_IMAGE="ghcr.io/ithute-stak/ithute-realtime" \
  MAILBOX_DNS_IMAGE_TAG="$DEPLOY_SHA" \
  docker compose -p "$CENTRAL_PROJECT" --env-file "$CENTRAL_ENV" $CENTRAL_FILES "$@"
}
central config >/dev/null
central up -d --no-build --no-deps --force-recreate ithute-auth ithute-auth-push-event-worker ithute-realtime
for service in ithute-auth ithute-auth-push-event-worker ithute-realtime; do
  id="$(central ps -q "$service")"
  [ -n "$id" ] || { echo "Central service did not start: $service" >&2; exit 1; }
  healthy=false
  for attempt in $(seq 1 90); do
    state="$(docker inspect "$id" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
    if [ "$state" = healthy ] || [ "$state" = running ]; then healthy=true; break; fi
    if [ "$state" = unhealthy ] || [ "$state" = exited ] || [ "$state" = dead ]; then break; fi
    sleep 2
  done
  [ "$healthy" = true ] || { central logs --tail=250 "$service" >&2 || true; exit 1; }
done
curl -fsS --retry 8 --retry-delay 3 https://auth.ithute.co.ls/healthz >/dev/null
curl -fsS --retry 8 --retry-delay 3 https://realtime.ithute.co.ls/healthz >/dev/null

# Start the new product after Central Auth/Realtime can recognize NBros.
cd "$RUNTIME_DIR"
compose up -d --no-build backend
BACKEND_ID="$(compose ps -q backend)"
[ -n "$BACKEND_ID" ] || { echo "NBros backend did not start" >&2; exit 1; }
backend_healthy=false
for attempt in $(seq 1 90); do
  state="$(docker inspect "$BACKEND_ID" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  if [ "$state" = healthy ]; then backend_healthy=true; break; fi
  if [ "$state" = unhealthy ] || [ "$state" = exited ] || [ "$state" = dead ]; then break; fi
  sleep 2
done
[ "$backend_healthy" = true ] || { compose logs --tail=250 backend >&2 || true; exit 1; }
curl -fsS "http://127.0.0.1:${NBROS_BACKEND_PORT:-8203}/readyz" >/dev/null

compose up -d --no-build fleet-monitor frontend
FRONTEND_ID="$(compose ps -q frontend)"
[ -n "$FRONTEND_ID" ] || { echo "NBros frontend did not start" >&2; exit 1; }
frontend_ready=false
for attempt in $(seq 1 90); do
  state="$(docker inspect "$FRONTEND_ID" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  if [ "$state" = healthy ] || [ "$state" = running ]; then frontend_ready=true; break; fi
  if [ "$state" = unhealthy ] || [ "$state" = exited ] || [ "$state" = dead ]; then break; fi
  sleep 2
done
[ "$frontend_ready" = true ] || { compose logs --tail=250 frontend >&2 || true; exit 1; }
curl -fsS "http://127.0.0.1:${NBROS_FRONTEND_PORT:-3203}/" >/dev/null

# Cut the existing nbro.ithute.co.ls virtual host over only after NBros is
# healthy. The shared certificate already contains this hostname from the
# earlier Nthane Brothers deployment; verify it before touching Nginx.
cd "$EDGE_DIR"
edge() { docker compose -p ithute-edge -f docker-compose.ithute-edge.yml "$@"; }
CERT_DOMAINS="$(edge run --rm --no-deps --entrypoint certbot certbot certificates 2>/dev/null | awk '
  /^[[:space:]]*Certificate Name:[[:space:]]*ithute-edge[[:space:]]*$/ { in_cert=1; next }
  in_cert && /^[[:space:]]*(Domains|Identifiers):[[:space:]]*/ { sub(/^[[:space:]]*(Domains|Identifiers):[[:space:]]*/, ""); print; exit }
  in_cert && /^[[:space:]]*Certificate Name:/ { exit }
')"
case " $CERT_DOMAINS " in
  *" $PRODUCT_HOST "*) : ;;
  *) echo "Shared TLS certificate does not contain $PRODUCT_HOST; refusing cutover" >&2; exit 1;;
esac
mkdir -p infrastructure/ithute-edge
cp "$EDGE_TEMPLATE" infrastructure/ithute-edge/default.conf.template
edge run --rm --no-deps --entrypoint /bin/sh edge-nginx -c '/docker-entrypoint.d/20-envsubst-on-templates.sh >/dev/null && nginx -t'
edge up -d --no-build --no-deps --force-recreate edge-nginx

edge_ready=false
for attempt in $(seq 1 45); do
  if edge exec -T edge-nginx nginx -T 2>/dev/null | grep -Fq 'server_name nbro.ithute.co.ls;' \
     && edge exec -T edge-nginx nginx -T 2>/dev/null | grep -Fq 'nbros-backend:8000'; then
    edge_ready=true; break
  fi
  sleep 2
done
[ "$edge_ready" = true ] || { edge logs --tail=250 edge-nginx >&2 || true; exit 1; }
edge exec -T edge-nginx nginx -t >/dev/null

# Public release gates.
for url in \
  "https://${PRODUCT_HOST}/healthz" \
  "https://${PRODUCT_HOST}/readyz" \
  "https://${PRODUCT_HOST}/"; do
  curl --fail --silent --show-error --retry 12 --retry-delay 5 --connect-timeout 10 --max-time 30 -o /dev/null "$url"
  echo "Verified: $url"
done
LOGIN_HEADERS="$(mktemp)"
curl --silent --show-error --max-time 30 -D "$LOGIN_HEADERS" -o /dev/null "https://${PRODUCT_HOST}/api/auth/login"
grep -Eiq '^location: https://auth\.ithute\.co\.ls/' "$LOGIN_HEADERS" || {
  echo "NBros login did not redirect to central Ithute Auth" >&2
  cat "$LOGIN_HEADERS" >&2
  rm -f "$LOGIN_HEADERS"
  exit 1
}
rm -f "$LOGIN_HEADERS"

echo | openssl s_client -connect "${PRODUCT_HOST}:443" -servername "$PRODUCT_HOST" 2>/dev/null \
  | openssl x509 -noout -ext subjectAltName | grep -F "$PRODUCT_HOST" >/dev/null

compose ps
echo "NBros production deployment completed at https://${PRODUCT_HOST} from ${DEPLOY_SHA}."
