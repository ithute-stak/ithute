#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml"

printf '\n== Phase 8: Phase 7 regression gate ==\n'
sh scripts/verify-phase7.sh

printf '\n== Phase 8: migrations ==\n'
$COMPOSE exec -T backend alembic upgrade head
HEAD_REV="$($COMPOSE exec -T backend alembic heads | awk 'NR==1 {print $1}')"
CURRENT_REV="$($COMPOSE exec -T backend alembic current | awk 'NR==1 {print $1}')"
[ -n "$HEAD_REV" ] && [ "$CURRENT_REV" = "$HEAD_REV" ]
$COMPOSE exec -T backend alembic history | grep -q '0005'

printf '\n== Phase 8: deliverability backend tests ==\n'
$COMPOSE exec -T backend pytest -q tests/test_deliverability.py tests/test_config_security.py

printf '\n== Phase 8: deliverability and operations API guards ==\n'
$COMPOSE exec -T backend python -c "from app.main import app; paths=set(app.openapi().get('paths', {})); required={'/api/v1/mail/operations/queue','/api/v1/mail/operations/queue/deferred','/api/v1/mail/operations/queue/summary','/api/v1/mail/operations/tls/status'}; assert required <= paths, required-paths; assert any(p.endswith('/deliverability/dkim') for p in paths); assert any(p.endswith('/deliverability/dkim/{key_id}/activate') for p in paths); assert any(p.endswith('/deliverability/readiness') for p in paths); assert any(p.endswith('/deliverability/dkim/sync') for p in paths); assert any(p.endswith('/deliverability/infrastructure-readiness') for p in paths)"
$COMPOSE exec -T backend python -c "from app.core.config import settings; assert '.' in settings.mail_hostname; assert len(settings.mail_ops_token) >= 24; assert settings.mail_tls_mode in {'selfsigned','acme','external'}"

printf '\n== Phase 8: rebuild mail services ==\n'
$COMPOSE build dovecot postfix
$COMPOSE up -d --force-recreate dovecot rspamd postfix

printf '\n== Phase 8: Rspamd DKIM signing configuration ==\n'
$COMPOSE exec -T rspamd rspamadm configtest
$COMPOSE exec -T rspamd sh -c "grep -q 'sign_authenticated = true' /etc/rspamd/local.d/dkim_signing.conf"
$COMPOSE exec -T rspamd sh -c "grep -q 'use_redis = true' /etc/rspamd/local.d/dkim_signing.conf"

printf '\n== Phase 8: inbound SMTP milter resolution ==\n'
SMTP_MASTER="$($COMPOSE exec -T postfix postconf -M smtp/inet)"
printf 'Postfix smtp master service: %s\n' "$SMTP_MASTER"
printf '%s\n' "$SMTP_MASTER" | awk '$1 == "smtp" && $2 == "inet" && $5 == "n" && $8 == "smtpd" { ok=1 } END { exit(ok ? 0 : 1) }'

printf '\n== Phase 8: outbound SMTP resolver access ==\n'
OUTBOUND_SMTP_MASTER="$($COMPOSE exec -T postfix postconf -M smtp/unix)"
printf 'Postfix outbound smtp transport: %s\n' "$OUTBOUND_SMTP_MASTER"
printf '%s\n' "$OUTBOUND_SMTP_MASTER" | awk '$1 == "smtp" && $2 == "unix" && $5 == "n" && $8 == "smtp" { ok=1 } END { exit(ok ? 0 : 1) }'

printf 'Waiting for rspamd Docker DNS resolution...\n'
RSPAMD_HOSTS=''
ATTEMPT=1
while [ "$ATTEMPT" -le 10 ]; do
  RSPAMD_HOSTS="$($COMPOSE exec -T postfix getent hosts rspamd 2>/dev/null || true)"
  if [ -n "$RSPAMD_HOSTS" ]; then
    break
  fi
  ATTEMPT=$((ATTEMPT + 1))
  sleep 1
done
if [ -z "$RSPAMD_HOSTS" ]; then
  printf 'ERROR: postfix container could not resolve rspamd after 10 attempts.\n' >&2
  $COMPOSE exec -T postfix cat /etc/resolv.conf || true
  $COMPOSE ps postfix rspamd || true
  exit 1
fi
printf 'rspamd resolves from postfix container: %s\n' "$RSPAMD_HOSTS"

printf 'Waiting for Postfix port 25 to return a real 220 banner through the milter path...\n'
SMTP_BANNER=''
ATTEMPT=1
while [ "$ATTEMPT" -le 15 ]; do
  SMTP_BANNER="$($COMPOSE exec -T postfix sh -c "printf 'QUIT\\r\\n' | nc -w 3 127.0.0.1 25" 2>/dev/null || true)"
  if printf '%s\n' "$SMTP_BANNER" | grep -q '^220 '; then
    break
  fi
  ATTEMPT=$((ATTEMPT + 1))
  sleep 2
done
printf 'SMTP banner: %s\n' "$SMTP_BANNER"
if ! printf '%s\n' "$SMTP_BANNER" | grep -q '^220 '; then
  printf 'ERROR: Postfix did not return a 220 banner after 15 attempts.\n' >&2
  $COMPOSE ps postfix rspamd || true
  $COMPOSE logs --no-color --tail=120 postfix rspamd || true
  exit 1
fi

printf '\n== Phase 8: SMTP abuse and sender-ownership controls ==\n'
$COMPOSE exec -T postfix postconf anvil_rate_time_unit | grep -q '60s'
$COMPOSE exec -T postfix postconf smtpd_client_connection_rate_limit | grep -q '60'
$COMPOSE exec -T postfix postconf smtpd_client_message_rate_limit | grep -q '120'
$COMPOSE exec -T postfix postconf smtpd_client_recipient_rate_limit | grep -q '240'
$COMPOSE exec -T postfix postconf smtpd_sender_login_maps | grep -q 'pgsql:/etc/postfix/pgsql-sender-login.cf'
$COMPOSE exec -T postfix postconf milter_mail_macros | grep -q '{auth_authen}'
$COMPOSE exec -T postfix postconf -P submission/inet/smtpd_sender_restrictions | grep -q 'reject_authenticated_sender_login_mismatch'
$COMPOSE run --rm --no-deps -e PYTHONPATH=/app -w /app backend python -c "import smtplib,ssl; c=smtplib.SMTP('postfix',587,timeout=10); c.ehlo(); c.starttls(context=ssl._create_unverified_context()); c.ehlo(); c.login('phase6@phase6.test','Phase6Strong!Pass'); code,msg=c.mail('spoof@phase6.test'); assert code < 400, (code,msg); code,msg=c.rcpt('phase6@phase6.test'); c.quit(); assert code >= 500, (code,msg); print('authenticated sender spoof rejected at RCPT stage:',code)"

printf '\n== Phase 8: private authenticated queue operations ==\n'
! $COMPOSE port postfix 9080 >/dev/null 2>&1
$COMPOSE exec -T backend python -c "from app.services.mail_ops import queue_summary,queue_deferred; s=queue_summary(); d=queue_deferred(); assert isinstance(s.get('queued'), int); assert isinstance(s.get('deferred'), int); assert isinstance(d.get('items'), list); print('mail queue summary:', s)"
$COMPOSE exec -T postfix python3 -c "import urllib.request,urllib.error; req=urllib.request.Request('http://127.0.0.1:9080/queue/summary',headers={'X-Mail-Ops-Token':'definitely-wrong-token-000000'}); ok=False
try: urllib.request.urlopen(req,timeout=3)
except urllib.error.HTTPError as e: ok=e.code==401
assert ok"
$COMPOSE exec -T postfix python3 /usr/local/bin/mailbox-mail-queue --summary >/dev/null

printf '\n== Phase 8: TLS certificate lifecycle ==\n'
sh -n scripts/deploy-mail-tls.sh
$COMPOSE exec -T backend python -c "from app.services.mail_ops import tls_status; r=tls_status(); assert r.get('certificate_present') is True; assert r.get('hostname_matches') is True; assert isinstance(r.get('days_remaining'), int); print('mail TLS status:', r)"
$COMPOSE exec -T postfix openssl x509 -in /etc/postfix/tls/cert.pem -noout -subject -issuer -enddate >/dev/null
$COMPOSE exec -T dovecot openssl x509 -in /etc/dovecot/tls/cert.pem -noout -subject -issuer -enddate >/dev/null

printf '\n== Phase 8: live DKIM synchronization and signing ==\n'
$COMPOSE run --rm --no-deps \
  -e PYTHONPATH=/app \
  -v "$(pwd)/scripts:/phase8-scripts:ro" \
  -w /app \
  backend python /phase8-scripts/phase8-dkim-signing-smoke.py

printf '\nPhase 8 FINAL acceptance verification PASSED.\n'
printf 'Verified staged-selector DKIM rotation and activation path, inbound SMTP milter DNS resolution, outbound SMTP resolver access, authenticated sender anti-spoofing, DKIM signing, PTR/HELO diagnostics, production TLS lifecycle, SMTP abuse controls, private queue operations and deferred/bounce visibility.\n'
printf 'Phase 8 is ready for acceptance and merge to main after user confirmation.\n'
