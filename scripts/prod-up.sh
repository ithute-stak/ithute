#!/usr/bin/env sh
set -eu
[ -f .env ] || { echo "Create a secure .env first: cp .env.example .env"; exit 1; }
set -a
. ./.env
set +a
sh scripts/prod-preflight.sh
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml -f docker-compose.phase12-monitoring.yml -f docker-compose.commercial-prod.yml"
if [ "${HA_MAIL_ENABLED:-false}" = "true" ]; then COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.ha-mail.yml"; fi
# shellcheck disable=SC2086
docker compose $COMPOSE_FILES config >/dev/null
# shellcheck disable=SC2086
docker compose $COMPOSE_FILES up -d --build
echo
echo "Mailbox DNS commercial production stack started."
echo "Panel:     https://${PANEL_HOSTNAME}"
echo "API:       https://${API_HOSTNAME}"
echo "Groupware: https://${GROUPWARE_HOSTNAME}"
if [ "${HA_MAIL_ENABLED:-false}" = "true" ]; then echo "Mail edge: HAProxy TCP edge on 25/587/993"; fi
echo "Authoritative secondary DNS must run on an independent server/failure domain."
echo "Backups must use an off-site repository before production launch."
