#!/usr/bin/env sh
set -eu

fail() {
  echo "Ithute platform production verification failed: $*" >&2
  exit 1
}

compose_file="docker-compose.ithute-platform.yml"
nginx_file="infrastructure/nginx/default.conf"
deploy_script="scripts/prod-deploy.sh"
workflow=".github/workflows/deploy-production.yml"
realtime_workflow=".github/workflows/ithute-realtime-production.yml"

for file in "$compose_file" "$nginx_file" "$deploy_script" "$workflow" "$realtime_workflow"; do
  [ -s "$file" ] || fail "missing required file $file"
done

# Database isolation is architectural, not optional. Auth, Push and Realtime each
# own their persistence; Realtime also has a dedicated Redis for fan-out/presence.
grep -q '^  ithute-auth-db:' "$compose_file" || fail "ithute-auth-db service is missing"
grep -q '^  ithute-push-db:' "$compose_file" || fail "ithute-push-db service is missing"
grep -q '^  ithute-realtime-db:' "$compose_file" || fail "ithute-realtime-db service is missing"
grep -q '^  ithute-realtime-redis:' "$compose_file" || fail "ithute-realtime-redis service is missing"
grep -q '^  ithute_auth_postgres:' "$compose_file" || fail "Auth volume is missing"
grep -q '^  ithute_push_postgres:' "$compose_file" || fail "Push volume is missing"
grep -q '^  ithute_realtime_postgres:' "$compose_file" || fail "Realtime database volume is missing"
grep -q '^  ithute_realtime_redis:' "$compose_file" || fail "Realtime Redis volume is missing"
grep -q 'AUTH_DATABASE_URL: postgresql+psycopg.*@ithute-auth-db:5432/' "$compose_file" || fail "Auth is not bound to its own DB"
grep -q 'PUSH_DATABASE_URL: postgresql+psycopg.*@ithute-push-db:5432/' "$compose_file" || fail "Push is not bound to its own DB"
grep -q 'REALTIME_DATABASE_URL: postgresql+psycopg.*@ithute-realtime-db:5432/' "$compose_file" || fail "Realtime is not bound to its own DB"
grep -q 'REALTIME_REDIS_URL: redis://ithute-realtime-redis:6379/0' "$compose_file" || fail "Realtime is not bound to its own Redis"

# The central APIs must be separate images/services. Products communicate over
# signed HTTP/WebSocket contracts and never read these databases directly.
grep -q 'ghcr.io/lelefe-dc/ithute-auth' "$compose_file" || fail "Auth production image is missing"
grep -q 'ghcr.io/lelefe-dc/ithute-push' "$compose_file" || fail "Push production image is missing"
grep -q 'ghcr.io/lelefe-dc/ithute-realtime' "$compose_file" || fail "Realtime production image is missing"
grep -q '^  ithute-push-worker:' "$compose_file" || fail "Push worker is missing"
grep -q 'REALTIME_AUTH_ISSUER:' "$compose_file" || fail "Realtime is not protected by central Auth"
grep -q 'REALTIME_PUSH_URL: http://ithute-push:8080' "$compose_file" || fail "Realtime is not connected to central Push"
grep -q 'PUSH_DELEGATED_SERVICE_CLIENTS:' "$compose_file" || fail "delegated Push allowlist is missing"

# Internal nginx is the single platform upstream used by the shared public edge.
grep -q 'server_name auth\.ithute\.co\.ls;' "$nginx_file" || fail "Auth hostname route is missing"
grep -q 'proxy_pass http://ithute-auth:8080;' "$nginx_file" || fail "Auth hostname is not routed to Auth"
grep -q 'server_name push\.ithute\.co\.ls;' "$nginx_file" || fail "Push hostname route is missing"
grep -q 'proxy_pass http://ithute-push:8080;' "$nginx_file" || fail "Push hostname is not routed to Push"
grep -q 'server_name realtime\.ithute\.co\.ls;' "$nginx_file" || fail "Realtime hostname route is missing"
grep -q 'proxy_pass http://ithute-realtime:8080/v1/ws;' "$nginx_file" || fail "Realtime WebSocket is not routed"
grep -q 'proxy_set_header Upgrade \$http_upgrade;' "$nginx_file" || fail "WebSocket upgrade header is missing"

# Production deployment must back up all central databases before migrations,
# wait for all APIs, and verify host-based routing through nginx.
grep -q 'ithute-auth-before-' "$deploy_script" || fail "Auth pre-release backup is missing"
grep -q 'ithute-push-before-' "$deploy_script" || fail "Push pre-release backup is missing"
grep -q 'ithute-realtime-before-' "$deploy_script" || fail "Realtime pre-release backup is missing"
grep -q 'wait_service ithute-auth ' "$deploy_script" || fail "Auth health gate is missing"
grep -q 'wait_service ithute-push ' "$deploy_script" || fail "Push health gate is missing"
grep -q 'wait_service ithute-realtime ' "$deploy_script" || fail "Realtime health gate is missing"
grep -q "Host: auth.ithute.co.ls" "$deploy_script" || fail "Auth nginx probe is missing"
grep -q "Host: push.ithute.co.ls" "$deploy_script" || fail "Push nginx probe is missing"
grep -q "Host: realtime.ithute.co.ls" "$deploy_script" || fail "Realtime nginx probe is missing"
grep -q 'ensure_random_hex ITHUTE_REALTIME_DB_PASSWORD' "$deploy_script" || fail "Realtime database password provisioning is missing"
grep -q 'ensure_random_hex ITHUTE_SERVICE_REALTIME_SECRET' "$deploy_script" || fail "Realtime Auth service secret provisioning is missing"
grep -q 'ithute-realtime:!thute Realtime' "$deploy_script" || fail "Realtime Auth registration is missing"
grep -q 'ITHUTE_PUSH_DELEGATED_SERVICE_CLIENTS' "$deploy_script" || fail "Realtime delegated Push provisioning is missing"

# Auth/Push remain in the shared release build. Realtime has its own validated
# immutable image publication workflow so its exact commit tag can be pulled by
# the shared production deployment.
grep -q 'ITHUTE_AUTH_IMAGE: ghcr.io/lelefe-dc/ithute-auth' "$workflow" || fail "Auth image build is missing"
grep -q 'ITHUTE_PUSH_IMAGE: ghcr.io/lelefe-dc/ithute-push' "$workflow" || fail "Push image build is missing"
grep -q 'openssl genpkey -algorithm RSA' "$workflow" || fail "Auth RSA key generation is missing"
grep -q 'ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY' "$workflow" || fail "Push endpoint encryption provisioning is missing"
grep -q 'ITHUTE_REALTIME_IMAGE: ghcr.io/lelefe-dc/ithute-realtime' "$realtime_workflow" || fail "Realtime image publication is missing"
grep -q './platform/ithute-realtime' "$realtime_workflow" || fail "Realtime Docker build context is missing"
grep -q 'workflow_run:' "$realtime_workflow" || fail "Realtime production publishing is not validation-gated"

# Provider/signing/service secrets are runtime-only. Test fixtures may contain
# unmistakably fake PEM-shaped strings, so scan deployed source while excluding
# test directories rather than treating fixtures as production credentials.
if grep -R -n -E --exclude='*.example' --exclude='verify-ithute-platform-production.sh' --exclude-dir='tests' \
  'BEGIN (EC |RSA )?PRIVATE KEY|"private_key"[[:space:]]*:[[:space:]]*"-----BEGIN' \
  platform/ithute-auth platform/ithute-push platform/ithute-realtime 2>/dev/null; then
  fail "private provider/signing credential material appears committed"
fi

echo "Ithute Auth + Push + Realtime production verification passed."
