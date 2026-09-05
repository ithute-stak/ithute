#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml -f docker-compose.phase12-monitoring.yml"

printf '\n== Phase 14: migrate edge schema ==\n'
$COMPOSE exec -T backend alembic upgrade head

printf '\n== Phase 14: edge backend regression ==\n'
$COMPOSE exec -T backend python -m pytest tests/test_edge_platform.py -q

printf '\n== Phase 14: edge API surface ==\n'
$COMPOSE exec -T backend python - <<'PY'
from app.main import app

routes = set(app.openapi().get("paths", {}))
required = {
    "/api/v1/tenants/{tenant_id}/edge/capabilities",
    "/api/v1/tenants/{tenant_id}/edge/applications",
    "/api/v1/tenants/{tenant_id}/edge/applications/{app_id}",
    "/api/v1/tenants/{tenant_id}/edge/applications/{app_id}/origins",
    "/api/v1/tenants/{tenant_id}/edge/applications/{app_id}/rules",
    "/api/v1/tenants/{tenant_id}/edge/applications/{app_id}/inspect",
    "/api/v1/tenants/{tenant_id}/edge/applications/{app_id}/inspections",
    "/api/v1/tenants/{tenant_id}/edge/domains/{domain_id}/dns-analytics",
    "/api/v1/tenants/{tenant_id}/edge/domains/{domain_id}/dns-analytics/snapshot",
}
missing = required - routes
assert not missing, f"missing edge routes: {sorted(missing)}"
print("!thute Edge API routes PASSED")
PY

printf '\n== Phase 14: migration and integration assertions ==\n'
CURRENT_REV="$($COMPOSE exec -T backend alembic current 2>/dev/null | awk 'NF {print $1; exit}')"
HEAD_REV="$($COMPOSE exec -T backend alembic heads 2>/dev/null | awk 'NF {print $1; exit}')"
[ -n "$CURRENT_REV" ] && [ "$CURRENT_REV" = "$HEAD_REV" ] || {
  echo "Alembic database is not at Phase 14 head: current=$CURRENT_REV head=$HEAD_REV" >&2
  exit 1
}

grep -q '0011_ithute_edge_platform' apps/backend/alembic/versions/0011_ithute_edge_platform.py
grep -q 'inspect_public_origin' apps/backend/app/services/edge_inspection.py
grep -q 'non-public IP address' apps/backend/app/services/edge_inspection.py
grep -q 'global_cdn' apps/backend/app/api/v1/edge.py
grep -q 'control_plane' apps/backend/app/api/v1/edge.py
test -f apps/frontend/app/edge/page.tsx
grep -q 'Edge control centre' apps/frontend/components/control-shell.tsx
test -f docs/PHASE-14-ITHUTE-EDGE-SECURITY.md
grep -q 'Global CDN' docs/PHASE-14-ITHUTE-EDGE-SECURITY.md

printf '\nITHUTE EDGE PHASE 14.1 verification PASSED.\n'
printf 'Verified migration head, edge regression tests, route registration, SSRF-safe inspection wiring, capability truth states, control-centre integration and Phase 14 documentation.\n'
