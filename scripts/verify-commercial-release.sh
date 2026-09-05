#!/usr/bin/env sh
set -eu

echo "== Commercial release: production dotenv parser =="
(
  . scripts/load-dotenv.sh
  load_dotenv .env.example
  [ "$APP_NAME" = "Mailbox DNS" ] || {
    echo "dotenv loader corrupted APP_NAME: $APP_NAME" >&2
    exit 1
  }
)

echo "== Commercial release: full Phase 13 regression =="
sh scripts/verify-phase13.sh

echo "== Commercial releases B/C: migration head and platform tests =="
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m pytest tests/test_business.py tests/test_commercial_platform.py tests/test_platform_setup.py tests/test_mail_dns_reconcile.py tests/test_transactional_mail_visibility.py -q

echo "== Commercial releases B/C: API surface =="
docker compose exec -T backend python - <<'PY'
from app.main import app
routes=set(app.openapi().get('paths', {}))
required={
    '/api/v1/public/pricing','/api/v1/public/signup','/api/v1/public/status',
    '/api/v1/public/platform-mode',
    '/api/v1/public/email-verification/request','/api/v1/public/email-verification/verify',
    '/api/v1/public/payment-provider','/api/v1/payments/dpo/callback',
    '/api/v1/platform/setup','/api/v1/platform/setup/domain',
    '/api/v1/platform/setup/verify','/api/v1/platform/setup/activate',
    '/api/v1/tenants/{tenant_id}/support/tickets','/api/v1/tenants/{tenant_id}/billing/manual-invoice',
    '/api/v1/tenants/{tenant_id}/billing/invoices/{invoice_id}/dpo-checkout',
    '/api/v1/tenants/{tenant_id}/professional-email/migrations/run',
    '/api/v1/tenants/{tenant_id}/professional-email/migrations/bulk/run',
    '/api/v1/tenants/{tenant_id}/professional-email/mailboxes/{mailbox_id}/delegates',
    '/api/v1/tenants/{tenant_id}/professional-email/mailboxes/{mailbox_id}/policy',
    '/api/v1/tenants/{tenant_id}/professional-email/mailboxes/{mailbox_id}/recover',
    '/api/v1/tenants/{tenant_id}/smtp-credentials','/api/v1/transactional/v1/send',
    '/api/v1/platform/resellers/{tenant_id}','/api/v1/tenants/{tenant_id}/reseller/brand',
    '/api/v1/tenants/{tenant_id}/registrar/register','/api/v1/tenants/{tenant_id}/groupware/credentials',
    '/api/v1/platform/mail-nodes','/api/v1/mail-nodes/{node_id}/heartbeat',
    '/api/v1/platform/business/summary',
    '/api/v1/tenants/{tenant_id}/domains/{domain_id}/dns/mail/reconcile'
}
missing=required-routes
assert not missing, f'missing commercial routes: {sorted(missing)}'
print('commercial B/C + platform bootstrap API routes PASSED')
PY

echo "== Commercial releases B/C: production frontend runner smoke test =="
docker build --target runner \
  --build-arg NEXT_PUBLIC_API_URL=/api/v1 \
  -t mailbox-dns-commercial-frontend-check ./apps/frontend >/dev/null

frontend_smoke="mailbox-dns-commercial-frontend-smoke"
cleanup_frontend_smoke() {
  docker rm -f "$frontend_smoke" >/dev/null 2>&1 || true
}
cleanup_frontend_smoke
trap cleanup_frontend_smoke 0 1 2 15

docker run -d --name "$frontend_smoke" \
  -e HOSTNAME=0.0.0.0 \
  -e PORT=3000 \
  mailbox-dns-commercial-frontend-check >/dev/null

frontend_ready=0
attempt=1
while [ "$attempt" -le 30 ]; do
  if docker exec "$frontend_smoke" node -e "const http=require('http');const req=http.get('http://127.0.0.1:3000/',res=>{res.resume();process.exit(res.statusCode>=200&&res.statusCode<400?0:1)});req.setTimeout(4000,()=>{req.destroy();process.exit(1)});req.on('error',()=>process.exit(1));" >/dev/null 2>&1; then
    frontend_ready=1
    break
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$frontend_smoke" 2>/dev/null || true)" != "true" ]; then
    break
  fi
  sleep 2
  attempt=$((attempt + 1))
done

if [ "$frontend_ready" -ne 1 ]; then
  echo "Production frontend runner failed IPv4 HTTP smoke test" >&2
  docker inspect -f '{{json .State}}' "$frontend_smoke" >&2 2>/dev/null || true
  docker logs "$frontend_smoke" >&2 2>/dev/null || true
  exit 1
fi

echo "production frontend runner IPv4 HTTP smoke test PASSED"
cleanup_frontend_smoke
trap - 0 1 2 15

echo "== Commercial releases B/C: Radicale fresh auth-volume smoke test =="
docker build -t mailbox-dns-commercial-radicale-check ./infra/radicale >/dev/null
radicale_smoke="mailbox-dns-commercial-radicale-smoke"
radicale_volume="mailbox-dns-commercial-radicale-auth-${$}"
cleanup_radicale_smoke() {
  docker rm -f "$radicale_smoke" >/dev/null 2>&1 || true
  docker volume rm "$radicale_volume" >/dev/null 2>&1 || true
}
cleanup_radicale_smoke
trap cleanup_radicale_smoke 0 1 2 15

docker volume create "$radicale_volume" >/dev/null
docker run -d --name "$radicale_smoke" \
  -v "$radicale_volume:/auth" \
  mailbox-dns-commercial-radicale-check >/dev/null

radicale_ready=0
attempt=1
while [ "$attempt" -le 30 ]; do
  if docker exec "$radicale_smoke" sh -c "test -f /auth/users" >/dev/null 2>&1 \
    && docker exec "$radicale_smoke" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5232/.web/', timeout=2)" >/dev/null 2>&1; then
    radicale_ready=1
    break
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$radicale_smoke" 2>/dev/null || true)" != "true" ]; then
    break
  fi
  sleep 2
  attempt=$((attempt + 1))
done

if [ "$radicale_ready" -ne 1 ]; then
  echo "Radicale failed fresh auth-volume smoke test" >&2
  docker inspect -f '{{json .State}}' "$radicale_smoke" >&2 2>/dev/null || true
  docker logs "$radicale_smoke" >&2 2>/dev/null || true
  exit 1
fi

echo "Radicale fresh auth-volume smoke test PASSED"
cleanup_radicale_smoke
trap - 0 1 2 15

echo "== Commercial releases B/C: unified production compose =="
BOOTSTRAP_PUBLIC_IP=1.1.1.1 PANEL_HOSTNAME=panel.example.co.ls API_HOSTNAME=api.example.co.ls GROUPWARE_HOSTNAME=groupware.example.co.ls ACME_EMAIL=ops@example.co.ls \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml -f docker-compose.phase12-monitoring.yml -f docker-compose.commercial-prod.yml config >/dev/null

echo "== Commercial releases B/C: HA mail compose =="
SMTP_PORT=2525 SUBMISSION_PORT=2587 IMAPS_PORT=2993 \
MAIL_EDGE_NODE1_HOST=mail-node-1.example.co.ls MAIL_EDGE_NODE2_HOST=mail-node-2.example.co.ls \
  docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.ha-mail.yml config >/dev/null

echo "== Commercial releases B/C: bootstrap and hardened Caddy generation =="
docker compose exec -T backend python - <<'PY'
from app.services.platform_setup import bootstrap_caddyfile, hardened_caddyfile, platform_names

bootstrap = bootstrap_caddyfile('1.1.1.1')
assert 'admin 0.0.0.0:2019' in bootstrap
assert 'http://1.1.1.1' in bootstrap
assert 'reverse_proxy backend:8000' in bootstrap
assert 'reverse_proxy frontend:3000' in bootstrap

names = platform_names('example.co.ls')
hardened = hardened_caddyfile(names, '1.1.1.1', 'ops@example.co.ls')
assert 'Strict-Transport-Security' in hardened
assert 'panel.example.co.ls' in hardened
assert 'api.example.co.ls' in hardened
assert 'groupware.example.co.ls' in hardened
print('bootstrap and hardened Caddy generation PASSED')
PY

echo "== Commercial releases B/C: static integration assertions =="
grep -q '0009_professional_hosting' apps/backend/alembic/versions/0009_professional_hosting.py
grep -q '0010_platform_self_domain' apps/backend/alembic/versions/0010_platform_self_domain.py
grep -q 'dovecot-sieve' infra/dovecot/Dockerfile
grep -q 'mail_plugins = quota acl' infra/dovecot/dovecot.conf
grep -q 'smtp-policy' docker-compose.phase6-mail.yml
grep -q 'radicale' docker-compose.phase6-mail.yml
grep -q 'mail-edge' docker-compose.ha-mail.yml
grep -q 'platform_runtime' docker-compose.commercial-prod.yml
grep -q 'BOOTSTRAP_PUBLIC_IP' docker-compose.yml
grep -q 'admin 0.0.0.0:2019' infrastructure/caddy/bootstrap.sh
grep -q 'branches: \[main\]' .github/workflows/deploy-production.yml
grep -q 'require_entitlement(db, tenant_id, "mailbox"' apps/backend/app/api/v1/mailboxes.py
grep -q 'tenant_id=payload.tenant_id' apps/backend/app/api/v1/identity.py
grep -q 'DPO_COMPANY_TOKEN' .env.example
grep -q 'OPENSRS_USERNAME' .env.example
grep -q 'PLATFORM_MODE=bootstrap' .env.example
grep -q 'Commercial Releases B and C' docs/COMMERCIAL-RELEASES-BC.md
test -f scripts/load-dotenv.sh
grep -q 'load_dotenv .env' scripts/prod-deploy.sh
grep -q 'load_dotenv .env' scripts/prod-preflight.sh
grep -q 'mail_dns_reconcile_cli' scripts/prod-deploy.sh
grep -q 'reconcile_mail_dns' apps/backend/app/api/v1/dns.py
test -f apps/backend/tests/test_mail_dns_reconcile.py
test -f apps/backend/tests/test_transactional_mail_visibility.py
grep -q "127.0.0.1:3000" docker-compose.prod.yml
grep -q "startup_diagnostics" scripts/prod-deploy.sh
test -x infra/radicale/entrypoint.sh || test -f infra/radicale/entrypoint.sh
grep -q '/auth/users' infra/radicale/entrypoint.sh
test -f apps/frontend/package-lock.json
grep -q 'npm ci' apps/frontend/Dockerfile
grep -q 'pip-audit==2.10.1' .github/workflows/phase13-regression.yml

echo
echo "COMMERCIAL RELEASES A+B+C verification PASSED."
echo "Verified Phase 13 regression, professional-email and hosting-company APIs, tenant entitlements, bootstrap-IP production mode, self-domain activation, automatic platform mail DNS/DKIM reconciliation, fail-closed signup controls without a third-party CAPTCHA, immutable deployment images, DPO/OpenSRS credential-gated adapters, groupware/mail data plane, recovery, and optional HA mail topology."
