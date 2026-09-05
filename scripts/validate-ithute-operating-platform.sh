#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

python -m py_compile \
  apps/backend/app/models/ithute_operating.py \
  apps/backend/app/models/mail_intelligence.py \
  apps/backend/app/services/ithute_operating.py \
  apps/backend/app/api/v1/ithute_operating_common.py \
  apps/backend/app/api/v1/ithute_operating_control.py \
  apps/backend/app/api/v1/ithute_operating_events.py \
  apps/backend/app/api/v1/ithute_operating_ops.py \
  apps/backend/app/api/v1/ithute_operating.py \
  apps/backend/app/api/v1/mail_intelligence.py \
  apps/backend/alembic/versions/0013_ithute_operating_core.py \
  apps/backend/alembic/versions/0014_ithute_operating_ops.py \
  apps/backend/alembic/versions/0015_mail_intelligence.py

for manifest in product.manifest.yaml products/LoanHub/product.manifest.yaml products/ithute-pay/product.manifest.yaml products/ithute-tutor/product.manifest.yaml; do
  test -s "$manifest"
  grep -Fq 'ownership: product' "$manifest"
  grep -Fq 'auth: central' "$manifest"
  grep -Fq 'push: central' "$manifest"
  grep -Fq 'realtime: central' "$manifest"
  grep -Fq 'event_bus: central' "$manifest"
done

LOANHUB_MANIFEST=products/LoanHub/product.manifest.yaml
grep -Fq 'require_pre_migration_backup: true' "$LOANHUB_MANIFEST"
grep -Fq 'reject_unexpected_volume_change: true' "$LOANHUB_MANIFEST"

grep -Fq 'VPS_PLATFORM_ROOT: /home/administrator/mailbox-dns' .github/workflows/loanhub-product-production.yml
grep -Fq 'BACKEND_IMAGE: ghcr.io/ithute-stak/loanhub-backend' .github/workflows/loanhub-product-production.yml
grep -Fq 'FRONTEND_IMAGE: ghcr.io/ithute-stak/loanhub-frontend' .github/workflows/loanhub-product-production.yml
grep -Fq 'EXPECTED_DB_VOLUME="${COMPOSE_PROJECT_NAME}_postgres_data"' .github/workflows/loanhub-product-production.yml
grep -Fq 'pg_dump -U "${DB_USER:-loanhub}" -d "${DB_NAME:-loan_db}" -Fc' .github/workflows/loanhub-product-production.yml
if grep -Eq 'docker (compose down -v|volume rm)' .github/workflows/loanhub-product-production.yml; then
  echo 'Destructive Docker volume command found in LoanHub production workflow.' >&2
  exit 1
fi

grep -Fq 'COMPOSE_PROJECT_NAME=loanhub' products/LoanHub/.env.production.example

# Active production publishing and Compose defaults must belong to the current
# GitHub organization. Old Lelefe-dc package paths cannot be pushed by this repo.
for file in \
  .github/workflows/deploy-production.yml \
  .github/workflows/ithute-pay-production.yml \
  .github/workflows/ithute-realtime-production.yml \
  .github/workflows/loanhub-product-production.yml \
  docker-compose.deploy.yml \
  docker-compose.deploy-ha.yml \
  docker-compose.ithute-platform.yml \
  docker-compose.ithute-pay.yml; do
  if grep -Fq 'ghcr.io/lelefe-dc/' "$file"; then
    echo "Legacy GHCR namespace remains in active deployment file: $file" >&2
    exit 1
  fi
done

grep -Fq 'ITHUTE_AUTH_IMAGE: ghcr.io/ithute-stak/ithute-auth' .github/workflows/deploy-production.yml
grep -Fq 'ITHUTE_PUSH_IMAGE: ghcr.io/ithute-stak/ithute-push' .github/workflows/deploy-production.yml
grep -Fq 'ITHUTE_REALTIME_IMAGE: ghcr.io/ithute-stak/ithute-realtime' .github/workflows/deploy-production.yml

echo 'Ithute operating-platform static validation passed.'
