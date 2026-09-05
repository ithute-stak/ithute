#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml"

printf '\n== Phase 9: Phase 8 regression gate ==\n'
sh scripts/verify-phase8.sh

printf '\n== Phase 9: rebuild application services ==\n'
$COMPOSE build backend frontend
$COMPOSE up -d --force-recreate backend frontend

printf '\n== Phase 9: backend syntax and final webmail route guards ==\n'
$COMPOSE exec -T backend python -m compileall -q app
$COMPOSE exec -T backend python -c "from app.main import app; paths=set(app.openapi().get('paths', {})); expected={'/api/v1/webmail/session','/api/v1/webmail/folders','/api/v1/webmail/folder-counts','/api/v1/webmail/messages','/api/v1/webmail/messages/{uid}','/api/v1/webmail/messages/{uid}/flags','/api/v1/webmail/messages/{uid}/move','/api/v1/webmail/messages/{uid}/attachments/{index}','/api/v1/webmail/drafts','/api/v1/webmail/signature','/api/v1/webmail/contacts','/api/v1/webmail/send','/api/v1/webmail/send-rich'}; missing=expected-paths; assert not missing, missing; print('webmail routes:', sorted(expected))"
$COMPOSE exec -T backend python -c "from app.services.webmail_polish import sanitize_html; value=sanitize_html('<p>ok</p><script>alert(1)</script>'); assert '<script' not in value.lower(); assert '<p>ok</p>' in value; print('HTML sanitizer guard PASSED')"

printf '\n== Phase 9: frontend production build ==\n'
docker build \
  --target builder \
  --build-arg "NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-http://localhost:8006/api/v1}" \
  -t mailbox-dns-frontend-phase9-check \
  ./apps/frontend

printf '\n== Phase 9: webmail route availability ==\n'
$COMPOSE exec -T frontend wget -qO- http://127.0.0.1:3000/webmail >/dev/null
$COMPOSE exec -T frontend wget -qO- http://127.0.0.1:3000/webmail/compose >/dev/null
$COMPOSE exec -T frontend wget -qO- http://127.0.0.1:3000/webmail/settings >/dev/null

printf '\n== Phase 9: foundation live mailbox login/send/receive ==\n'
$COMPOSE run --rm --no-deps -e PYTHONPATH=/app -v "$(pwd)/scripts:/phase9-scripts:ro" -w /app backend python /phase9-scripts/phase9-webmail-smoke.py

printf '\n== Phase 9: live actions, search, drafts and attachments ==\n'
$COMPOSE run --rm --no-deps -e PYTHONPATH=/app -v "$(pwd)/scripts:/phase9-scripts:ro" -w /app backend python /phase9-scripts/phase9-webmail-actions-smoke.py

printf '\n== Phase 9: final HTML, contacts, counts and spam lifecycle ==\n'
$COMPOSE run --rm --no-deps -e PYTHONPATH=/app -v "$(pwd)/scripts:/phase9-scripts:ro" -w /app backend python /phase9-scripts/phase9-webmail-final-smoke.py

printf '\nPhase 9 FINAL acceptance verification PASSED.\n'
printf 'Verified secure sessions, live IMAP/SMTP, server-side search, pagination, flags, reply/forward threading, move/archive/delete, Drafts, attachments, sanitized HTML composition, signatures, contacts/autocomplete, folder unread counts, Junk/restore controls, responsive webmail routes and production frontend build.\n'
printf 'Phase 9 is ready for acceptance and fast-forward merge to main after user confirmation.\n'
