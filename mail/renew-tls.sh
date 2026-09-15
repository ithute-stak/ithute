#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
MAIL_DIR="${ITHUTE_MAIL_DIR:-/home/administrator/ithute-platform-mail}"
ENV_FILE="$APP_DIR/.env.production"
IMAGE_ENV_FILE="$APP_DIR/.image.env"
MAIL_HOST="mail.ithute.co.ls"
CERT_EMAIL="${ITHUTE_CERT_EMAIL:-thekoetlisi@ithute.co.ls}"
CERTBOT_IMAGE="certbot/certbot:v5.8.0"
MAILSERVER_IMAGE="ghcr.io/docker-mailserver/docker-mailserver:15.1.0"

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

cert_files_ready() {
  docker run --rm --pull=never \
    -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt:ro" \
    --entrypoint /bin/sh \
    "$CERTBOT_IMAGE" -c \
      "test -s '/etc/letsencrypt/live/$MAIL_HOST/fullchain.pem' && test -s '/etc/letsencrypt/live/$MAIL_HOST/privkey.pem'"
}

cert_valid_for_30_days() {
  cert_files_ready || return 1
  docker run --rm --pull=never \
    -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt:ro" \
    --entrypoint openssl \
    "$MAILSERVER_IMAGE" x509 \
      -checkend $((30 * 24 * 60 * 60)) \
      -noout \
      -in "/etc/letsencrypt/live/$MAIL_HOST/fullchain.pem" >/dev/null 2>&1
}

docker image inspect "$CERTBOT_IMAGE" >/dev/null 2>&1 || {
  echo "Missing preloaded Certbot image: $CERTBOT_IMAGE" >&2
  exit 1
}
docker image inspect "$MAILSERVER_IMAGE" >/dev/null 2>&1 || {
  echo "Missing preloaded mail image: $MAILSERVER_IMAGE" >&2
  exit 1
}

# Do nothing while the certificate is comfortably valid. Certbot's archive
# files are root-owned, so validation happens inside the bind-mounted runtime
# instead of through the unprivileged SSH user's host filesystem permissions.
if cert_valid_for_30_days; then
  echo "Mail TLS certificate is valid for more than 30 days; renewal skipped."
  exit 0
fi

restart_caddy() {
  app_compose start caddy >/dev/null 2>&1 || true
}
trap restart_caddy EXIT

app_compose stop caddy >/dev/null

if ! cert_files_ready; then
  echo "Mail TLS live lineage is incomplete; forcing repair for $MAIL_HOST."
  docker run --rm --pull=never -p 80:80 \
    -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt" \
    "$CERTBOT_IMAGE" certonly \
      --standalone \
      --non-interactive \
      --agree-tos \
      --no-eff-email \
      --force-renewal \
      --cert-name "$MAIL_HOST" \
      --email "$CERT_EMAIL" \
      -d "$MAIL_HOST"
else
  docker run --rm --pull=never -p 80:80 \
    -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt" \
    "$CERTBOT_IMAGE" renew --standalone --non-interactive --quiet
fi

restart_caddy
trap - EXIT

if ! cert_files_ready; then
  echo "Mail TLS renewal completed but the expected certificate/key are unavailable to the mail runtime." >&2
  docker run --rm --pull=never \
    -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt" \
    "$CERTBOT_IMAGE" certificates >&2 || true
  exit 1
fi

mail_compose up -d --pull never --force-recreate mailserver
