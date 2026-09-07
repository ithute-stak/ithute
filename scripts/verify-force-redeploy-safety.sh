#!/usr/bin/env sh
set -eu

# Guard the deployment paths used by the manual full-platform force redeploy.
# A force redeploy may recreate containers and refresh images/configuration, but
# it must never delete persistent volumes or deliberately erase production data.
FILES="
.github/workflows/deploy-production.yml
.github/workflows/enforce-production-domain-identity.yml
.github/workflows/ithute-pay-production.yml
.github/workflows/ithute-pay-dns.yml
.github/workflows/ithute-tutor-production.yml
.github/workflows/loanhub-product-production.yml
.github/workflows/shared-tls-edge-production.yml
.github/workflows/production-storage-recovery.yml
scripts/ithute-tutor-deploy.sh
scripts/prod-deploy.sh
scripts/prod-preflight.sh
scripts/prod-storage-preflight.sh
"

for file in $FILES; do
  [ -f "$file" ] || { echo "Missing force-redeploy dependency: $file" >&2; exit 1; }
done

forbidden() {
  expression="$1"
  label="$2"
  if grep -En "$expression" $FILES >/tmp/force-redeploy-forbidden.txt 2>/dev/null; then
    echo "Force redeploy safety violation: $label" >&2
    cat /tmp/force-redeploy-forbidden.txt >&2
    rm -f /tmp/force-redeploy-forbidden.txt
    exit 1
  fi
  rm -f /tmp/force-redeploy-forbidden.txt
}

forbidden 'docker[[:space:]]+compose[^\n]*down[^\n]*(--volumes|-v)([[:space:]]|$)' 'docker compose down with volume deletion'
forbidden 'compose[[:space:]]+down[^\n]*(--volumes|-v)([[:space:]]|$)' 'compose down with volume deletion'
forbidden 'docker[[:space:]]+volume[[:space:]]+rm([[:space:]]|$)' 'docker volume rm'
forbidden 'docker[[:space:]]+volume[[:space:]]+prune([[:space:]]|$)' 'docker volume prune'
forbidden 'docker[[:space:]]+system[[:space:]]+prune[^\n]*--volumes' 'docker system prune --volumes'
forbidden 'docker[[:space:]]+compose[^\n]*rm[^\n]*(--volumes|-v)([[:space:]]|$)' 'docker compose rm with volume deletion'
forbidden 'rm[[:space:]]+-rf[[:space:]]+[^\n]*(postgres|powerdns|mail|uploads|media|backups|platform-secrets)' 'recursive deletion of production data paths'

# Core production deploy must take database backups before application services
# are brought up. These markers are intentionally strict so a future refactor
# cannot silently remove the backup gate from the force-deploy path.
grep -Fq 'Creating pre-release application database backup' scripts/prod-deploy.sh
grep -Fq 'Creating pre-release PowerDNS database backup' scripts/prod-deploy.sh
grep -Fq 'Creating pre-release !thute Auth database backup' scripts/prod-deploy.sh
grep -Fq 'Creating pre-release !thute Push database backup' scripts/prod-deploy.sh
grep -Fq 'Creating pre-release !thute Realtime database backup' scripts/prod-deploy.sh

# Production storage recovery may reclaim reproducible images/build cache and
# expired pre-release rollback snapshots, but it must remain volume-safe and the
# normal production preflight must require it before pulling a new release.
grep -Fq 'prod-storage-preflight.sh cleanup' scripts/prod-preflight.sh
grep -Fq 'Persistent Docker volumes are never pruned' scripts/prod-storage-preflight.sh
grep -Fq 'docker builder prune -af' scripts/prod-storage-preflight.sh
grep -Fq 'docker image prune -af' scripts/prod-storage-preflight.sh
grep -Fq 'No persistent volume or live database data was deleted.' scripts/prod-storage-preflight.sh

# All production-mutating paths must continue to use the shared VPS lock. Tutor
# now owns that lock inside its checked-in remote deploy script rather than in a
# large inline GitHub Actions heredoc.
for file in \
  scripts/prod-deploy.sh \
  .github/workflows/ithute-pay-production.yml \
  scripts/ithute-tutor-deploy.sh \
  .github/workflows/loanhub-product-production.yml \
  .github/workflows/shared-tls-edge-production.yml \
  .github/workflows/production-storage-recovery.yml; do
  grep -Fq '/tmp/ithute-production.lock' "$file" || {
    echo "Missing shared production host lock in $file" >&2
    exit 1
  }
done

# Pay and Tutor explicitly recreate their application containers while leaving
# their data services/volumes intact. Tutor's recreation commands now live in
# the checked-in deploy script that executes on the VPS.
grep -Fq -- '--force-recreate' .github/workflows/ithute-pay-production.yml
grep -Fq -- '--force-recreate tutor-backend' scripts/ithute-tutor-deploy.sh
grep -Fq -- '--force-recreate tutor-frontend' scripts/ithute-tutor-deploy.sh

# LoanHub uses an even stricter preservation path: it refuses to deploy if the
# existing PostgreSQL volume is missing or mounted under an unexpected name,
# and it takes a pre-migration backup before application services are updated.
grep -Fq 'Expected existing LoanHub database volume not found' .github/workflows/loanhub-product-production.yml
grep -Fq 'LoanHub database volume mismatch' .github/workflows/loanhub-product-production.yml
grep -Fq 'loanhub-pre-migrate-' .github/workflows/loanhub-product-production.yml
grep -Fq 'Pre-migration PostgreSQL backup is empty or missing; aborting.' .github/workflows/loanhub-product-production.yml

echo 'Full-platform force redeploy safety contract passed: persistent data deletion is not permitted.'
