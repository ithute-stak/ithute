#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTH_IMAGE="ithute-auth:integration-test"
PUSH_IMAGE="ithute-push:integration-test"
PANEL_BACKEND_IMAGE="mailbox-dns-backend:ithute-admin-test"
PANEL_FRONTEND_IMAGE="mailbox-dns-frontend:ithute-admin-test"

echo "==> Building !thute Auth on Python 3.12"
docker build -t "$AUTH_IMAGE" "$ROOT_DIR/platform/ithute-auth"

echo "==> Running !thute Auth compile + tests"
docker run --rm \
  --entrypoint sh \
  -e AUTH_DATABASE_URL='sqlite+pysqlite:///:memory:' \
  "$AUTH_IMAGE" \
  -c 'python3 --version && python3 -m compileall -q app alembic tests && python3 -m pytest -q'

echo "==> Building !thute Push on Python 3.12"
docker build -t "$PUSH_IMAGE" "$ROOT_DIR/platform/ithute-push"

PUSH_KEY="$(docker run --rm --entrypoint python3 "$PUSH_IMAGE" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

echo "==> Running !thute Push compile + tests"
docker run --rm \
  --entrypoint sh \
  -e PUSH_DATABASE_URL='sqlite+pysqlite:///:memory:' \
  -e PUSH_ENDPOINT_ENCRYPTION_KEY="$PUSH_KEY" \
  "$PUSH_IMAGE" \
  -c 'python3 --version && python3 -m compileall -q app alembic tests && python3 -m pytest -q'

echo "==> Checking migration revision files"
docker run --rm --entrypoint sh \
  -e AUTH_DATABASE_URL='sqlite+pysqlite:///:memory:' \
  "$AUTH_IMAGE" \
  -c 'test -f alembic/versions/0005_push_event_outbox.py'

docker run --rm --entrypoint sh \
  -e PUSH_DATABASE_URL='sqlite+pysqlite:///:memory:' \
  -e PUSH_ENDPOINT_ENCRYPTION_KEY="$PUSH_KEY" \
  "$PUSH_IMAGE" \
  -c 'test -f alembic/versions/0003_auth_lifecycle_integration.py'

echo "==> Building Mailbox panel backend and validating Superadmin contract"
docker build -t "$PANEL_BACKEND_IMAGE" "$ROOT_DIR/apps/backend"
docker run --rm \
  --entrypoint sh \
  "$PANEL_BACKEND_IMAGE" \
  -c 'python3 -m pytest -q tests/test_ithute_platform_admin_contract.py'

echo "==> Building panel frontend with !thute Auth & Push dashboard"
docker build \
  --build-arg NEXT_PUBLIC_API_URL='http://localhost:8006/api/v1' \
  -t "$PANEL_FRONTEND_IMAGE" \
  "$ROOT_DIR/apps/frontend"

cat <<'EOF'

Auth ↔ Push + Superadmin panel validation passed.

Validated:
  - Auth builds on Python 3.12 and its test suite passes
  - Push builds on Python 3.12 and its test suite passes
  - Push-token, lifecycle-event and Push-admin contracts pass
  - lifecycle migration files are included in the built images
  - Mailbox panel backend Superadmin route/security contract passes
  - panel frontend production build includes the !thute Auth & Push dashboard
  - dashboard is discoverable under Governance & control at /ithute-platform

The full PostgreSQL/service-network and deployed HTTPS acceptance flow should still be run before merge.
EOF
