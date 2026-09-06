#!/usr/bin/env sh
set -eu

: "${APP_DIR:=/home/administrator/mailbox-dns/loanhub}"
: "${MAILBOX_APP_DIR:=/home/administrator/mailbox-dns}"

cd "$APP_DIR"
[ -s .env.production ] || { echo "LoanHub production environment is missing" >&2; exit 1; }
[ -s compose.yaml ] || { echo "LoanHub production compose.yaml is missing" >&2; exit 1; }
[ -s compose.nginx-edge.yaml ] || { echo "Nginx edge compose override is missing" >&2; exit 1; }
[ -s "$APP_DIR/.edge/bin/deploy-mail-tls.sh" ] || { echo "Mail TLS deploy helper is missing" >&2; exit 1; }

set -a
. ./.env.production
set +a
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-loanhub}"
export LOANHUB_ENV_FILE=.env.production
export EDGE_CERTBOT_CONFIG_DIR="${EDGE_CERTBOT_CONFIG_DIR:-$APP_DIR/.edge/letsencrypt}"
export EDGE_ACME_WEBROOT="${EDGE_ACME_WEBROOT:-$APP_DIR/.edge/acme-webroot}"

edge_compose() {
  docker compose --env-file .env.production -f compose.yaml -f compose.nginx-edge.yaml "$@"
}

tmp_mail="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_mail"
}
trap cleanup 0 1 2 15
chmod 700 "$tmp_mail"

edge_compose --profile nginx-edge-tools run --rm --no-deps --entrypoint cat certbot \
  /etc/letsencrypt/live/ithute-edge/fullchain.pem > "$tmp_mail/fullchain.pem"
edge_compose --profile nginx-edge-tools run --rm --no-deps --entrypoint cat certbot \
  /etc/letsencrypt/live/ithute-edge/privkey.pem > "$tmp_mail/privkey.pem"
chmod 600 "$tmp_mail/privkey.pem"

(
  cd "$MAILBOX_APP_DIR"
  sh "$APP_DIR/.edge/bin/deploy-mail-tls.sh" "$tmp_mail/fullchain.pem" "$tmp_mail/privkey.pem"
)

trap - 0 1 2 15
cleanup
echo "Postfix and Dovecot now use the current Certbot Ithute edge certificate."
