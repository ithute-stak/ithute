#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml"

printf '\n== Phase 6: Phase 5 regression gate ==\n'
sh scripts/verify-phase5.sh

printf '\n== Phase 6: compose configuration ==\n'
$COMPOSE config >/dev/null

printf '\n== Phase 6: build mail images ==\n'
$COMPOSE build unbound postfix dovecot

printf '\n== Phase 6: start mail data plane ==\n'
$COMPOSE up -d postgres redis powerdns-db powerdns backend frontend unbound rspamd dovecot postfix

printf '\n== Phase 6: database-backed fixture ==\n'
$COMPOSE run --rm --no-deps -e PYTHONPATH=/app -v "$(pwd)/scripts:/phase6-scripts:ro" backend \
  sh -c 'cd /app && python /phase6-scripts/phase6-seed-fixture.py'

printf '\n== Phase 6: mail service health ==\n'
$COMPOSE exec -T unbound dig @127.0.0.1 . SOA +time=2 +tries=1 >/dev/null
$COMPOSE exec -T rspamd rspamadm configtest >/dev/null
$COMPOSE exec -T rspamd sh -c "grep -q '172.31.56.53' /etc/rspamd/local.d/options.inc"
$COMPOSE exec -T dovecot doveconf -n >/dev/null
$COMPOSE exec -T dovecot doveadm auth test phase6@phase6.test 'Phase6Strong!Pass' | grep -q 'auth succeeded'
$COMPOSE exec -T postfix postfix check
$COMPOSE exec -T postfix postconf smtpd_milters | grep -q 'rspamd:11332'
$COMPOSE exec -T postfix postconf virtual_transport | grep -q 'dovecot:24'
$COMPOSE exec -T postfix postmap -q phase6.test pgsql:/etc/postfix/pgsql-virtual-domains.cf | grep -q '^1$'
$COMPOSE exec -T postfix postmap -q phase6@phase6.test pgsql:/etc/postfix/pgsql-virtual-mailboxes.cf | grep -q '^1$'

printf '\n== Phase 6: relay rejection check ==\n'
$COMPOSE run --rm --no-deps backend python - <<'PY'
import smtplib
smtp = smtplib.SMTP('postfix', 25, timeout=10)
smtp.ehlo()
try:
    smtp.mail('outside@example.net')
    code, _ = smtp.rcpt('recipient@example.org')
    if code < 500:
        raise SystemExit(f'unauthenticated relay unexpectedly accepted with SMTP {code}')
finally:
    smtp.quit()
PY

printf '\n== Phase 6: authenticated end-to-end mail flow ==\n'
$COMPOSE run --rm --no-deps -v "$(pwd)/scripts:/phase6-scripts:ro" backend python /phase6-scripts/phase6-mail-smoke.py

printf '\n== Phase 6: persistence check ==\n'
$COMPOSE restart dovecot >/dev/null
for attempt in $(seq 1 20); do
  if $COMPOSE exec -T dovecot doveconf -n >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 20 ]; then
    echo 'Dovecot did not become ready after restart.' >&2
    exit 1
  fi
  sleep 1
done
$COMPOSE exec -T dovecot sh -c "find /srv/vmail -type f | grep -q ."

printf '\n== Phase 6: frontend/backend regression smoke ==\n'
curl -fsS http://localhost:${BACKEND_PORT:-8006}/health/ready >/dev/null
curl -fsS http://localhost:${FRONTEND_PORT:-3006}/ >/dev/null

printf '\nPhase 6 verification PASSED.\n'
printf 'Verified PostgreSQL-backed mailbox lookup, local recursive DNS for Rspamd, STARTTLS submission, SMTP AUTH, relay rejection, LMTP delivery, persistent Maildir storage and IMAPS retrieval.\n'
printf 'The Phase 6 credential and self-signed certificates remain development-only fixtures.\n'
