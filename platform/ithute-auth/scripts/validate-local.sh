#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE="${ITHUTE_AUTH_TEST_IMAGE:-ithute-auth:test}"
BASE_URL="${ITHUTE_AUTH_LOCAL_URL:-http://localhost:8088}"

echo "==> Building !thute Auth test image"
docker build -t "$IMAGE" .

echo "==> Running Python 3.12 compile and pytest suite"
docker run --rm \
  --entrypoint sh \
  "$IMAGE" \
  -c 'python3 --version && python3 -m compileall -q app alembic tests && python3 -m pytest -q'

if [[ ! -f .env || ! -f secrets/jwt-private.pem || ! -f secrets/jwt-public.pem ]]; then
  echo "==> Unit/contract validation passed."
  echo "==> Integration validation skipped because .env or local JWT keys are missing."
  exit 0
fi

echo "==> Starting local PostgreSQL + Auth integration stack"
docker compose up -d --build

echo "==> Waiting for Auth health"
ready=0
for _ in $(seq 1 45); do
  if curl -fsS "$BASE_URL/healthz" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "Auth did not become healthy." >&2
  docker compose ps >&2 || true
  docker compose logs --tail=150 auth >&2 || true
  exit 1
fi

echo "==> Checking OIDC discovery and JWKS"
curl -fsS "$BASE_URL/.well-known/openid-configuration" >/dev/null
curl -fsS "$BASE_URL/.well-known/jwks.json" >/dev/null

echo "==> Checking Alembic state"
docker compose exec -T auth alembic current
docker compose exec -T auth alembic heads

echo "==> Checking security headers"
headers_file="$(mktemp)"
trap 'rm -f "$headers_file"' EXIT
curl -fsS -D "$headers_file" -o /dev/null "$BASE_URL/account/login"
grep -qi '^x-content-type-options: nosniff' "$headers_file"
grep -qi '^x-frame-options: DENY' "$headers_file"
grep -qi '^referrer-policy: no-referrer' "$headers_file"
grep -qi '^cache-control: no-store' "$headers_file"
grep -qi '^content-security-policy:' "$headers_file"

if [[ "$BASE_URL" == https://* ]]; then
  grep -qi '^strict-transport-security:' "$headers_file"
fi

echo "==> Current containers"
docker compose ps

echo "==> !thute Auth local validation passed"
