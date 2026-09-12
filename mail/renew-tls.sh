#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute}"
MAIL_DIR="${ITHUTE_MAIL_DIR:-/home/administrator/ithute-mail}"
ENV_FILE="$APP_DIR/.env.production"

app_compose() {
  docker compose --env-file "$ENV_FILE" -p ithute -f "$APP_DIR/compose.production.yml" "$@"
}
mail_compose() {
  docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" "$@"
}

restart_caddy() {
  app_compose start caddy >/dev/null 2>&1 || true
}
trap restart_caddy EXIT

app_compose stop caddy >/dev/null

docker run --rm -p 80:80 \
  -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt" \
  certbot/certbot:latest renew --standalone --non-interactive --quiet

restart_caddy
trap - EXIT
mail_compose up -d --force-recreate mailserver
