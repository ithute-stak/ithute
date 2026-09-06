#!/usr/bin/env sh
set -eu

: "${APP_DIR:?APP_DIR is required}"
: "${MAILBOX_APP_DIR:?MAILBOX_APP_DIR is required}"
: "${EXPECTED_IP:?EXPECTED_IP is required}"
: "${MAIL_TLS_DEPLOY_SCRIPT:?MAIL_TLS_DEPLOY_SCRIPT is required}"

cd "$APP_DIR"
[ -s .env.production ] || { echo "LoanHub production environment is missing" >&2; exit 1; }
[ -s compose.yaml ] || { echo "LoanHub production compose.yaml is missing" >&2; exit 1; }
[ -s compose.nginx-edge.yaml ] || { echo "Nginx edge compose override is missing" >&2; exit 1; }
[ -s infra/nginx-edge/default.conf.template ] || { echo "Nginx edge template is missing" >&2; exit 1; }
[ -s infra/nginx-edge/acme-bootstrap.conf ] || { echo "ACME bootstrap config is missing" >&2; exit 1; }
[ -s infra/nginx-edge/proxy-common.conf ] || { echo "Nginx proxy snippet is missing" >&2; exit 1; }
[ -s "$MAIL_TLS_DEPLOY_SCRIPT" ] || { echo "Mail TLS deployment script is missing" >&2; exit 1; }

set -a
. ./.env.production
set +a

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-loanhub}"
export LOANHUB_ENV_FILE=.env.production
APP_DOMAIN="${APP_DOMAIN:-loanhub.co.ls}"
API_DOMAIN="${API_DOMAIN:-api.loanhub.co.ls}"
WWW_DOMAIN="${WWW_DOMAIN:-www.loanhub.co.ls}"
SANDBOX_APP_DOMAIN="${SANDBOX_APP_DOMAIN:-sandbox.loanhub.co.ls}"
SANDBOX_API_DOMAIN="${SANDBOX_API_DOMAIN:-api-sandbox.loanhub.co.ls}"

EDGE_CERTBOT_CONFIG_DIR="${EDGE_CERTBOT_CONFIG_DIR:-$APP_DIR/.edge/letsencrypt}"
EDGE_ACME_WEBROOT="${EDGE_ACME_WEBROOT:-$APP_DIR/.edge/acme-webroot}"
export EDGE_CERTBOT_CONFIG_DIR EDGE_ACME_WEBROOT
mkdir -p "$EDGE_CERTBOT_CONFIG_DIR" "$EDGE_ACME_WEBROOT"

edge_compose() {
  docker compose --env-file .env.production -f compose.yaml -f compose.nginx-edge.yaml "$@"
}
base_compose() {
  docker compose --env-file .env.production -f compose.yaml "$@"
}

# A stable ACME contact is required even if an old production .env still carries
# the template placeholder from the original Caddy deployment.
ACME_EMAIL="${TLS_EMAIL:-}"
case "$ACME_EMAIL" in
  ""|admin@example.com|replace-with-real-admin-email)
    ACME_EMAIL="supperadmin@ithute.co.ls"
    ;;
esac

ITHUTE_HOSTS="ithute.co.ls www.ithute.co.ls panel.ithute.co.ls api.ithute.co.ls auth.ithute.co.ls push.ithute.co.ls realtime.ithute.co.ls tutor.ithute.co.ls groupware.ithute.co.ls pay.ithute.co.ls api.pay.ithute.co.ls portal.pay.ithute.co.ls mail.ithute.co.ls"
LOANHUB_HOSTS="$APP_DOMAIN $API_DOMAIN $WWW_DOMAIN $SANDBOX_APP_DOMAIN $SANDBOX_API_DOMAIN"
ALL_HOSTS="$ITHUTE_HOSTS $LOANHUB_HOSTS"

command -v dig >/dev/null 2>&1 || { echo "dig is required on the production VPS" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl is required on the production VPS" >&2; exit 1; }

# Fail before touching the current edge if any ACME hostname cannot reach this VPS.
for host in $ALL_HOSTS; do
  if ! dig +short A "$host" | grep -Fx "$EXPECTED_IP" >/dev/null; then
    echo "DNS preflight failed: $host does not resolve to $EXPECTED_IP" >&2
    dig +short A "$host" >&2 || true
    exit 1
  fi
  echo "DNS verified: $host -> $EXPECTED_IP"
done

# Ensure the existing application networks/upstreams are present before we take
# Caddy off ports 80/443.
docker network inspect mailbox-dns_mailbox_dns >/dev/null 2>&1 || {
  echo "Mailbox-DNS shared Docker network is missing" >&2
  exit 1
}
for service in frontend backend sandbox_frontend sandbox_backend; do
  id="$(base_compose ps -q "$service")"
  [ -n "$id" ] || { echo "Required LoanHub service is missing: $service" >&2; exit 1; }
  state="$(docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || true)"
  [ "$state" = running ] || { echo "Required LoanHub service is not running: $service ($state)" >&2; exit 1; }
done

caddy_id="$(base_compose ps -q caddy 2>/dev/null || true)"
[ -n "$caddy_id" ] || { echo "Current Caddy edge is not running; refusing a cutover without rollback" >&2; exit 1; }
[ "$(docker inspect -f '{{.State.Status}}' "$caddy_id" 2>/dev/null || true)" = running ] || {
  echo "Current Caddy edge is not in running state" >&2
  exit 1
}

rollback_needed=false
cleanup() {
  status=$?
  trap - 0 1 2 15
  if [ "$status" -ne 0 ] && [ "$rollback_needed" = true ]; then
    echo "Nginx edge cutover failed; restoring the previous Caddy edge." >&2
    edge_compose stop nginx-edge certbot-renew nginx-acme-bootstrap >/dev/null 2>&1 || true
    base_compose up -d caddy >/dev/null 2>&1 || true
    restored=false
    for attempt in $(seq 1 18); do
      if curl -sS --connect-timeout 5 --max-time 15 -o /dev/null https://portal.pay.ithute.co.ls/portal; then
        restored=true
        break
      fi
      sleep 5
    done
    if [ "$restored" = true ]; then
      echo "Caddy rollback verified on https://portal.pay.ithute.co.ls/portal" >&2
    else
      echo "Caddy rollback could not be verified; dumping edge logs." >&2
      base_compose logs --tail=250 caddy >&2 || true
    fi
  fi
  exit "$status"
}
trap cleanup 0
trap 'exit 130' 1 2 15

# Stop only the public edge. Application/database containers remain untouched.
base_compose stop caddy
rollback_needed=true

# Use a tiny HTTP-only Nginx while certificates are issued. This avoids needing
# certificates merely to start the final Nginx configuration.
edge_compose --profile nginx-edge-bootstrap up -d nginx-acme-bootstrap
bootstrap_id="$(edge_compose --profile nginx-edge-bootstrap ps -q nginx-acme-bootstrap)"
[ -n "$bootstrap_id" ] || { echo "ACME bootstrap Nginx was not created" >&2; exit 1; }
for attempt in $(seq 1 20); do
  if curl -fsS --connect-timeout 2 --max-time 5 http://127.0.0.1/ >/dev/null; then
    break
  fi
  [ "$attempt" -lt 20 ] || { edge_compose logs --tail=100 nginx-acme-bootstrap >&2 || true; exit 1; }
  sleep 1
done

edge_compose --profile nginx-edge-tools run --rm --no-deps certbot certonly \
  --webroot -w /var/www/certbot \
  --non-interactive --agree-tos --email "$ACME_EMAIL" --keep-until-expiring --expand \
  --cert-name ithute-edge \
  -d ithute.co.ls \
  -d www.ithute.co.ls \
  -d panel.ithute.co.ls \
  -d api.ithute.co.ls \
  -d auth.ithute.co.ls \
  -d push.ithute.co.ls \
  -d realtime.ithute.co.ls \
  -d tutor.ithute.co.ls \
  -d groupware.ithute.co.ls \
  -d pay.ithute.co.ls \
  -d api.pay.ithute.co.ls \
  -d portal.pay.ithute.co.ls \
  -d mail.ithute.co.ls

edge_compose --profile nginx-edge-tools run --rm --no-deps certbot certonly \
  --webroot -w /var/www/certbot \
  --non-interactive --agree-tos --email "$ACME_EMAIL" --keep-until-expiring --expand \
  --cert-name loanhub-edge \
  -d "$APP_DOMAIN" \
  -d "$API_DOMAIN" \
  -d "$WWW_DOMAIN" \
  -d "$SANDBOX_APP_DOMAIN" \
  -d "$SANDBOX_API_DOMAIN"

edge_compose stop nginx-acme-bootstrap
edge_compose --profile nginx-edge up -d nginx-edge certbot-renew

nginx_id="$(edge_compose --profile nginx-edge ps -q nginx-edge)"
[ -n "$nginx_id" ] || { echo "Nginx edge container was not created" >&2; exit 1; }
for attempt in $(seq 1 30); do
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$nginx_id" 2>/dev/null || true)"
  case "$health" in
    healthy|running) break ;;
    unhealthy|exited|dead)
      edge_compose logs --tail=250 nginx-edge >&2 || true
      exit 1
      ;;
  esac
  [ "$attempt" -lt 30 ] || { edge_compose logs --tail=250 nginx-edge >&2 || true; exit 1; }
  sleep 2
done
edge_compose exec -T nginx-edge nginx -t

# Reuse the public mail certificate for SMTP/IMAP. Extract through the Certbot
# container so the host user never needs direct access to Certbot's private-key mode.
tmp_mail="$(mktemp -d)"
chmod 700 "$tmp_mail"
edge_compose --profile nginx-edge-tools run --rm --no-deps --entrypoint cat certbot \
  /etc/letsencrypt/live/ithute-edge/fullchain.pem > "$tmp_mail/fullchain.pem"
edge_compose --profile nginx-edge-tools run --rm --no-deps --entrypoint cat certbot \
  /etc/letsencrypt/live/ithute-edge/privkey.pem > "$tmp_mail/privkey.pem"
chmod 600 "$tmp_mail/privkey.pem"
(
  cd "$MAILBOX_APP_DIR"
  sh "$MAIL_TLS_DEPLOY_SCRIPT" "$tmp_mail/fullchain.pem" "$tmp_mail/privkey.pem"
)
rm -rf "$tmp_mail"

# Persist fail-closed mail TLS for future Postfix/Dovecot recreations now that a
# valid public certificate is installed in their existing TLS volumes.
mail_env="$MAILBOX_APP_DIR/.env"
if [ -f "$mail_env" ]; then
  tmp_env="$(mktemp)"
  awk 'index($0, "MAIL_TLS_MODE=") != 1 { print }' "$mail_env" > "$tmp_env"
  printf '%s\n' 'MAIL_TLS_MODE=external' >> "$tmp_env"
  cat "$tmp_env" > "$mail_env"
  rm -f "$tmp_env"
  chmod 600 "$mail_env"
fi

# Validate the TLS handshake for every hostname. HTTP status is intentionally not
# constrained here because APIs may validly return 401/404 at their root path.
for host in $ALL_HOSTS; do
  verified=false
  for attempt in $(seq 1 12); do
    if curl -sS --connect-timeout 5 --max-time 15 -o /dev/null "https://$host/"; then
      verified=true
      break
    fi
    sleep 3
  done
  [ "$verified" = true ] || {
    echo "HTTPS/TLS verification failed: https://$host/" >&2
    edge_compose logs --tail=250 nginx-edge >&2 || true
    exit 1
  }
  echo "TLS verified: $host"
done

# Auth is the release gate: in addition to a valid certificate, its actual public
# health endpoint must be reachable before owner synchronization is allowed.
auth_healthy=false
for attempt in $(seq 1 18); do
  if curl -fsS --connect-timeout 5 --max-time 15 https://auth.ithute.co.ls/healthz >/dev/null; then
    auth_healthy=true
    break
  fi
  sleep 5
done
[ "$auth_healthy" = true ] || {
  echo "Central Auth is not healthy through the new Nginx TLS edge" >&2
  edge_compose logs --tail=250 nginx-edge >&2 || true
  exit 1
}

rollback_needed=false
trap - 0 1 2 15
echo "Nginx + Certbot shared production edge cutover completed successfully."
