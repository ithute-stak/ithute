#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
MAIL_DIR="${ITHUTE_MAIL_DIR:-/home/administrator/ithute-platform-mail}"
SOURCE_DIR="${ITHUTE_SOURCE_DIR:-$APP_DIR}"
MAIL_HOST="mail.ithute.co.ls"
EXPECTED_IPV4="${ITHUTE_VPS_IPV4:-204.12.205.224}"
CERT_EMAIL="${ITHUTE_CERT_EMAIL:-thekoetlisi@ithute.co.ls}"
MAILSERVER_IMAGE="ghcr.io/docker-mailserver/docker-mailserver:15.1.0"
CERTBOT_IMAGE="certbot/certbot:v5.8.0"
DOMAINS=(ithute.co.ls lelefadebtcollectors.co.ls lelefachambers.co.ls tjekatjeka.co.ls)

if [ "$MAIL_DIR" = "/" ] || [ "$MAIL_DIR" = "/home" ] || [ "$MAIL_DIR" = "/home/administrator" ]; then
  echo "Unsafe Ithute mail directory: $MAIL_DIR" >&2
  exit 2
fi
if [ "$APP_DIR" = "$MAIL_DIR" ]; then
  echo "Application and mail directories must be separate." >&2
  exit 2
fi

test -f "$APP_DIR/.env.production" || { echo "Missing $APP_DIR/.env.production" >&2; exit 2; }
test -f "$APP_DIR/.image.env" || { echo "Missing $APP_DIR/.image.env" >&2; exit 2; }
test -f "$APP_DIR/compose.production.yml" || { echo "Missing $APP_DIR/compose.production.yml" >&2; exit 2; }
test -f "$SOURCE_DIR/mail/compose.yml" || { echo "Missing mail compose template in $SOURCE_DIR" >&2; exit 2; }
test -f "$SOURCE_DIR/mail/renew-tls.sh" || { echo "Missing mail TLS script in $SOURCE_DIR" >&2; exit 2; }

# Production is image-only. Registry access belongs on the GitHub runner; the
# VPS must already have the exact mail and Certbot images loaded before this
# bootstrap is allowed to change runtime state.
docker image inspect "$MAILSERVER_IMAGE" >/dev/null 2>&1 || {
  echo "Missing preloaded mail image: $MAILSERVER_IMAGE" >&2
  exit 4
}
docker image inspect "$CERTBOT_IMAGE" >/dev/null 2>&1 || {
  echo "Missing preloaded Certbot image: $CERTBOT_IMAGE" >&2
  exit 4
}

mkdir -p "$MAIL_DIR" "$MAIL_DIR/config" "$MAIL_DIR/accounts" "$MAIL_DIR/data/mail-data" "$MAIL_DIR/data/mail-state" "$MAIL_DIR/data/mail-logs" "$MAIL_DIR/letsencrypt"
cp "$SOURCE_DIR/mail/compose.yml" "$MAIL_DIR/compose.yml"
cp "$SOURCE_DIR/mail/renew-tls.sh" "$MAIL_DIR/renew-tls.sh"
chmod 700 "$MAIL_DIR/renew-tls.sh"

DNS_FILE="$MAIL_DIR/mail-dns-required.txt"
{
  echo "Mail host required before TLS provisioning:"
  echo "$MAIL_HOST A $EXPECTED_IPV4"
  echo
  for domain in "${DOMAINS[@]}"; do
    echo "$domain MX 10 $MAIL_HOST"
    echo "$domain TXT \"v=spf1 mx -all\""
    echo "_dmarc.$domain TXT \"v=DMARC1; p=quarantine; rua=mailto:info@$domain; adkim=s; aspf=s\""
    echo
  done
  echo "Also set the VPS reverse-DNS/PTR to: $MAIL_HOST"
} > "$DNS_FILE"
chmod 600 "$DNS_FILE"

if ! getent ahostsv4 "$MAIL_HOST" 2>/dev/null | awk '{print $1}' | grep -Fxq "$EXPECTED_IPV4"; then
  echo "Mail DNS is not ready: $MAIL_HOST must resolve to $EXPECTED_IPV4." >&2
  echo "Required records are staged in $DNS_FILE" >&2
  exit 3
fi

app_compose() {
  docker compose \
    --env-file "$APP_DIR/.env.production" \
    --env-file "$APP_DIR/.image.env" \
    -p ithute \
    -f "$APP_DIR/compose.production.yml" \
    "$@"
}
mail_compose() {
  docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" "$@"
}

# Certbot writes archive material as root-owned files. The SSH deployment user
# may not be able to stat those symlink targets on the host even though the
# certificate is valid and readable by the mail container. Validate from a
# root process inside the same bind mount instead of using host-side `test -s`.
cert_files_ready() {
  docker run --rm --pull=never \
    -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt:ro" \
    --entrypoint /bin/sh \
    "$CERTBOT_IMAGE" -c \
      "test -s '/etc/letsencrypt/live/$MAIL_HOST/fullchain.pem' && test -s '/etc/letsencrypt/live/$MAIL_HOST/privkey.pem'"
}

if ! cert_files_ready; then
  restart_caddy() { app_compose start caddy >/dev/null 2>&1 || true; }
  trap restart_caddy EXIT
  app_compose stop caddy >/dev/null

  # A previous interrupted Certbot run can leave renewal metadata claiming the
  # certificate is still valid while the live lineage is incomplete. Force a
  # repair only when the certificate/key are genuinely unavailable inside the
  # bind mount. Once repaired, scheduled finalizers skip certificate issuance.
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

  restart_caddy
  trap - EXIT
  if ! cert_files_ready; then
    echo "Certbot completed but the expected mail certificate lineage is still incomplete." >&2
    docker run --rm --pull=never \
      -v "$MAIL_DIR/letsencrypt:/etc/letsencrypt" \
      "$CERTBOT_IMAGE" certificates >&2 || true
    exit 1
  fi
fi

# Never pull on the VPS. The GitHub workflow loads these images first.
# The first start deliberately uses the legacy account file so Docker
# Mailserver's setup helper can safely provision any missing bootstrap accounts.
mail_compose up -d --pull never

for attempt in $(seq 1 30); do
  if docker exec ithute-mail setup help >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    mail_compose logs --tail=150 >&2 || true
    echo "Mail server did not become ready for account provisioning." >&2
    exit 1
  fi
  sleep 2
done

CREDENTIALS_FILE="$MAIL_DIR/mailbox-credentials.txt"
touch "$CREDENTIALS_FILE"
chmod 600 "$CREDENTIALS_FILE"

new_password() {
  openssl rand -base64 24 | tr '/+' '_-' | tr -d '=\n'
}

for domain in "${DOMAINS[@]}"; do
  address="info@$domain"
  password="$(new_password)"
  if add_output="$(docker exec ithute-mail setup email add "$address" "$password" 2>&1)"; then
    printf '%s %s\n' "$address" "$password" >> "$CREDENTIALS_FILE"
    echo "Mailbox created: $address"
  elif printf '%s\n' "$add_output" | grep -Fq "'$address' already exists"; then
    echo "Mailbox already exists: $address"
  else
    printf '%s\n' "$add_output" >&2
    exit 1
  fi
  unset password add_output

  postmaster="postmaster@$domain"
  if ! docker exec ithute-mail setup alias list 2>/dev/null | grep -Fq "$postmaster"; then
    docker exec ithute-mail setup alias add "$postmaster" "$address" || true
  fi
done

# Keep mailbox credentials in a narrow shared directory instead of exposing the
# full Docker Mailserver config (including DKIM private keys) to the application
# API. Migrate existing accounts without overwriting newer application-managed
# hashes: entries already present in the isolated account file win, while legacy
# external-domain accounts are retained. Run this as container root so it also
# works if an earlier application deployment created the shared file as root.
docker run --rm --pull=never \
  -v "$MAIL_DIR/config:/legacy-config" \
  -v "$MAIL_DIR/accounts:/mail-accounts" \
  --entrypoint /bin/sh \
  "$MAILSERVER_IMAGE" -c '
    set -eu
    accounts=/mail-accounts/postfix-accounts.cf
    legacy=/legacy-config/postfix-accounts.cf
    touch "$accounts"
    chmod 600 "$accounts"
    if [ -f "$legacy" ] && [ ! -L "$legacy" ]; then
      tmp=/mail-accounts/.postfix-accounts.migrate
      awk -F"|" '\''
        index($0, "|") { key=tolower($1); if (!seen[key]++) print; next }
        { print }
      '\'' "$accounts" "$legacy" > "$tmp"
      chmod 600 "$tmp"
      mv "$tmp" "$accounts"
    fi
    rm -f "$legacy"
    ln -s /mail-accounts/postfix-accounts.cf "$legacy"
  '

# Docker Mailserver owns the OpenDKIM key files. Do not loosen host filesystem
# permissions just so the deployment account can read them. Inspect and export
# the public DNS records from inside the running mail container, where the
# config bind mount is available at /tmp/docker-mailserver.
if ! docker exec ithute-mail test -s "/tmp/docker-mailserver/opendkim/keys/ithute.co.ls/mail.txt" >/dev/null 2>&1; then
  docker exec ithute-mail setup config dkim domain "$(IFS=,; echo "${DOMAINS[*]}")"
fi

mail_compose up -d --pull never --force-recreate mailserver

{
  echo
  echo "DKIM records generated by Docker Mailserver:"
  for domain in "${DOMAINS[@]}"; do
    keyfile="/tmp/docker-mailserver/opendkim/keys/$domain/mail.txt"
    if ! docker exec ithute-mail test -s "$keyfile" >/dev/null 2>&1; then
      echo "Missing DKIM DNS record for $domain inside Docker Mailserver: $keyfile" >&2
      exit 1
    fi
    echo
    echo "--- $domain / mail._domainkey.$domain ---"
    docker exec ithute-mail cat "$keyfile"
  done
} >> "$DNS_FILE"

CRON_LINE="17 3 * * 1 ITHUTE_APP_DIR=$APP_DIR ITHUTE_MAIL_DIR=$MAIL_DIR $MAIL_DIR/renew-tls.sh >>$MAIL_DIR/tls-renew.log 2>&1"
(
  crontab -l 2>/dev/null | grep -vF "$MAIL_DIR/renew-tls.sh" || true
  echo "$CRON_LINE"
) | crontab -

mail_compose ps
touch "$MAIL_DIR/.ithute-mail-finalized" "$MAIL_DIR/.account-sync-v1"
printf '\nMail accounts are provisioned. Credentials: %s\n' "$CREDENTIALS_FILE"
printf 'DNS records: %s\n' "$DNS_FILE"
printf 'Mail finalization marker: %s\n' "$MAIL_DIR/.ithute-mail-finalized"
printf 'Do not consider Internet mail complete until MX/SPF/DKIM/DMARC and PTR are applied and verified.\n'
