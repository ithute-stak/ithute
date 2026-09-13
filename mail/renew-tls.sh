#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
MAIL_DIR="${ITHUTE_MAIL_DIR:-/home/administrator/ithute-platform-mail}"
ENV_FILE="$APP_DIR/.env.production"
IMAGE_ENV_FILE="$APP_DIR/.image.env"
MAIL_HOST="mail.ithute.co.ls"
CERT_FILE="$MAIL_DIR/letsencrypt/live/$MAIL_HOST/fullchain.pem"
CERTBOT_IMAGE="certbot/certbot:v5.8.0"

app_compose() {
  docker compose \
    --env-file "$ENV_FILE" \
    --env-file "$IMAGE_ENV_FILE" \
    -p ithute \
    -f "$APP_DIR/compose.production.yml" \
    "$@"
}
mail_compose() {
  docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" "$@"
}

# Do nothing while the certificate is comfortably valid. This avoids the old
# weekly Caddy interruption when Certbot would only report "not yet due".
if [ -s "$CERT_FILE" ] && openssl x509 -checkend $((30 * 24 * 60 * 60)) -noout -in "$CERT_FILE" >/dev/null 2>&1; then
  echo "Mail TLS certificate is valid for more than 30 days; renewal skipped."
  exit 0
fi

docker image inspect "$CERTBOT_IMAGE" >/dev/null 2>&1 || {
  echo "Missing preloaded Certbot image: $CERTBOT_IMAGE" >&2
  exit 1
}

restart_caddy() {
  app_compose start caddy >/dev/null 2>&1 || true
}
trap restart_caddy EXIT

app_compose stop caddy >/dev/null

docker run --rm --pull=never -p 80:80 \
  -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt" \
  "$CERTBOT_IMAGE" renew --standalone --non-interactive --quiet

restart_caddy
trap - EXIT
mail_compose up -d --pull never --force-recreate mailserver
