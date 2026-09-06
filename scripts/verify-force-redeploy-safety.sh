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
scripts/prod-deploy.sh
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

# All production-mutating paths must continue to use the shared VPS lock.
for file in \
  scripts/prod-deploy.sh \
  .github/workflows/ithute-pay-production.yml \
  .github/workflows/ithute-tutor-production.yml \
  .github/workflows/loanhub-product-production.yml \
  .github/workflows/shared-tls-edge-production.yml; do
  grep -Fq '/tmp/ithute-production.lock' "$file" || {
    echo "Missing shared production host lock in $file" >&2
    exit 1
  }
done

# The force action is container recreation, not data recreation.
grep -Fq -- '--force-recreate' .github/workflows/ithute-pay-production.yml
grep -Fq -- '--force-recreate' .github/workflows/ithute-tutor-production.yml
grep -Fq -- '--force-recreate' .github/workflows/loanhub-product-production.yml

echo 'Full-platform force redeploy safety contract passed: persistent data deletion is not permitted.'
