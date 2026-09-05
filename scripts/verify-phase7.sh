#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml"

printf '\n== Phase 7: Phase 6 regression gate ==\n'
sh scripts/verify-phase6.sh

printf '\n== Phase 7: migrations ==\n'
$COMPOSE exec -T backend alembic upgrade head
HEAD_REV="$($COMPOSE exec -T backend alembic heads | awk 'NR==1 {print $1}')"
CURRENT_REV="$($COMPOSE exec -T backend alembic current | awk 'NR==1 {print $1}')"
[ -n "$HEAD_REV" ] && [ "$CURRENT_REV" = "$HEAD_REV" ]
$COMPOSE exec -T backend alembic history | grep -q '0004'

printf '\n== Phase 7: rebuild dynamic mail services ==\n'
$COMPOSE build postfix dovecot
$COMPOSE up -d --force-recreate postfix dovecot

printf '\n== Phase 7: mailbox backend tests ==\n'
$COMPOSE exec -T backend pytest -q tests/test_mailboxes.py

printf '\n== Phase 7: dynamic mail data-plane maps ==\n'
$COMPOSE exec -T postfix postconf virtual_mailbox_domains | grep -q 'pgsql:'
$COMPOSE exec -T postfix postconf virtual_mailbox_maps | grep -q 'pgsql:'
$COMPOSE exec -T postfix postconf virtual_alias_maps | grep -q 'pgsql:'
$COMPOSE exec -T dovecot doveconf -n | grep -q 'driver = sql'
$COMPOSE exec -T postfix postmap -q phase6.test pgsql:/etc/postfix/pgsql-virtual-domains.cf | grep -q '^1$'
$COMPOSE exec -T postfix postmap -q phase6@phase6.test pgsql:/etc/postfix/pgsql-virtual-mailboxes.cf | grep -q '^1$'
$COMPOSE exec -T dovecot doveadm auth test phase6@phase6.test 'Phase6Strong!Pass' | grep -q 'auth succeeded'

printf '\n== Phase 7: quota enforcement configuration ==\n'
printf '  - checking Dovecot quota plugin\n'
$COMPOSE exec -T dovecot doveconf -n | grep -q 'mail_plugins = quota'
printf '  - checking IMAP quota plugin\n'
$COMPOSE exec -T dovecot doveconf -n | grep -q 'imap_quota'
printf '  - checking Maildir quota backend\n'
$COMPOSE exec -T dovecot doveconf -n | grep -q 'quota = maildir:User quota'
printf '  - checking SQL quota rule source\n'
$COMPOSE exec -T dovecot sh -c "grep -q \"'\\*:bytes=' || m.quota_bytes::text AS quota_rule\" /etc/dovecot/dovecot-sql.conf.ext"
printf '  - checking live mailbox user lookup\n'
$COMPOSE exec -T dovecot doveadm user phase6@phase6.test >/dev/null
printf '  quota enforcement configuration PASSED\n'

printf '\n== Phase 7: tenant/domain suspension guards ==\n'
$COMPOSE exec -T postfix sh -c "grep -q \"t.status='active'\" /etc/postfix/pgsql-virtual-mailboxes.cf"
$COMPOSE exec -T postfix sh -c "grep -q \"d.status='verified'\" /etc/postfix/pgsql-virtual-mailboxes.cf"
$COMPOSE exec -T dovecot sh -c "grep -q \"t.status='active'\" /etc/dovecot/dovecot-sql.conf.ext"
$COMPOSE exec -T dovecot sh -c "grep -q \"d.mail_enabled=true\" /etc/dovecot/dovecot-sql.conf.ext"

printf '\n== Phase 7: live API-created mailbox lifecycle ==\n'
$COMPOSE run --rm --no-deps \
  -e PYTHONPATH=/app \
  -v "$(pwd)/scripts:/phase7-scripts:ro" \
  -w /app \
  backend \
  python /phase7-scripts/phase7-live-mailbox-smoke.py

printf '\n== Phase 7: no static mailbox source of truth ==\n'
! $COMPOSE exec -T postfix postconf virtual_mailbox_maps | grep -q 'hash:/etc/postfix/vmailbox'
! $COMPOSE exec -T dovecot doveconf -n | grep -q 'passwd-file'

printf '\nPhase 7 verification PASSED.\n'
printf 'Verified database mailbox schema/API tests, immediate API-created mailbox activation, SMTP/IMAP delivery, suspend/restore enforcement, archive lifecycle, tenant/domain guards, and per-mailbox Dovecot quota rules.\n'
printf 'Mailbox, alias and distribution-group administration uses the same live PostgreSQL source of truth without mail-service restart or static map regeneration.\n'
