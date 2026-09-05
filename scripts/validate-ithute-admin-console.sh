#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_IMAGE="mailbox-dns-backend:ithute-admin-test"
FRONTEND_IMAGE="mailbox-dns-frontend:ithute-admin-test"

echo "==> Validating Auth ↔ Push foundation"
bash "$ROOT_DIR/scripts/validate-auth-push-integration.sh"

echo "==> Building panel backend on Python 3.12"
docker build -t "$BACKEND_IMAGE" "$ROOT_DIR/apps/backend"

echo "==> Compiling panel backend and running admin-console contract tests"
docker run --rm --entrypoint sh \
  -e SECRET_KEY='ithute-admin-validation-secret-key-1234567890' \
  -e DATABASE_URL='sqlite+pysqlite:///:memory:' \
  "$BACKEND_IMAGE" \
  -c 'python3 -m compileall -q app tests && python3 -m pytest -q tests/test_ithute_platform_admin_contract.py'

echo "==> Building production panel frontend"
docker build --target builder \
  --build-arg NEXT_PUBLIC_API_URL='https://api.ithute.co.ls/api/v1' \
  -t "$FRONTEND_IMAGE" \
  "$ROOT_DIR/apps/frontend"

cat <<'EOF'

!thute platform superadmin console validation passed.

Validated:
  - Auth ↔ Push foundation and contract suites
  - panel backend Python compilation
  - dual-gate / PKCE / HttpOnly admin-console contract tests
  - production Next.js build including /ithute-platform

Still perform the live acceptance flow before merge:
  platform owner -> !thute step-up -> combined dashboard -> revoke session ->
  confirm Push lifecycle projection -> end elevated session.
EOF
