#!/usr/bin/env sh
set -eu

: "${EDGE_DIR:?EDGE_DIR is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${TUTOR_HOST:?TUTOR_HOST is required}"

staged_template="${TUTOR_EDGE_TEMPLATE:-/tmp/ithute-edge-tutor-${DEPLOY_SHA}.conf}"
live_template="$EDGE_DIR/infrastructure/ithute-edge/default.conf.template"
health_host="${EDGE_HEALTH_HOST:-panel.ithute.co.ls}"

mkdir -p "$EDGE_DIR/infrastructure/ithute-edge"
if [ -s "$staged_template" ]; then
  cp "$staged_template" "$live_template"
  rm -f "$staged_template"
elif [ ! -s "$live_template" ]; then
  echo "Tutor edge template is missing: $staged_template and $live_template" >&2
  exit 1
fi

cd "$EDGE_DIR"
[ -f docker-compose.ithute-edge.yml ] || {
  echo "Missing shared edge compose file in $EDGE_DIR" >&2
  exit 1
}

edge_compose() {
  docker compose -p ithute-edge -f docker-compose.ithute-edge.yml "$@"
}

edge_compose config >/dev/null

current_sans="$(mktemp)"
required_sans="$(mktemp)"
required_tmp="$(mktemp)"
cleanup() {
  rm -f "$current_sans" "$required_sans" "$required_tmp"
}
trap cleanup EXIT HUP INT TERM

# The ithute-edge certificate is shared by every HTTPS virtual host. Never
# derive the next certificate only from the currently served SAN set because a
# damaged or product-only certificate would then become the new source of
# truth. Start from the complete Ithute edge identity instead.
cat > "$required_sans" <<EOF
ithute.co.ls
www.ithute.co.ls
panel.ithute.co.ls
api.ithute.co.ls
auth.ithute.co.ls
push.ithute.co.ls
realtime.ithute.co.ls
groupware.ithute.co.ls
mail.ithute.co.ls
pay.ithute.co.ls
api.pay.ithute.co.ls
portal.pay.ithute.co.ls
tutor.ithute.co.ls
$TUTOR_HOST
EOF

# The same edge also terminates LoanHub production and sandbox TLS. Resolve the
# effective Compose environment rather than hard-coding values that operators
# may override on the VPS.
edge_compose run --rm --no-deps --entrypoint /bin/sh edge-nginx -c \
  'printf "%s\n" "$APP_DOMAIN" "$WWW_DOMAIN" "$API_DOMAIN" "$SANDBOX_APP_DOMAIN" "$SANDBOX_API_DOMAIN"' \
  >> "$required_sans"

awk 'NF && !seen[$0]++ { print }' "$required_sans" > "$required_tmp"
mv "$required_tmp" "$required_sans"

# Read the certificate directly from the shared Let's Encrypt volume through a
# fresh one-shot edge container. A running Nginx container can retain the old
# certificate symlink target after Certbot atomically replaces it; using that
# stale view here would cause unnecessary issuance and, more importantly, can
# hide the fact that a correct certificate is already ready to be activated.
current_cert="$(edge_compose run --rm --no-deps --entrypoint /bin/sh edge-nginx -c \
  'command -v openssl >/dev/null 2>&1 || exit 127; openssl x509 -in /etc/letsencrypt/live/ithute-edge/fullchain.pem -noout -ext subjectAltName' \
  2>/dev/null || true)"
printf '%s\n' "$current_cert" \
  | tr ',' '\n' \
  | sed -n 's/^[[:space:]]*DNS://p' \
  | sed 's/[[:space:]]//g' \
  | sed '/^$/d' > "$current_sans"

if [ ! -s "$current_sans" ]; then
  echo 'No readable canonical certificate was found in the shared volume; issuance will be attempted.'
fi

needs_issue=false
while IFS= read -r domain; do
  [ -n "$domain" ] || continue
  if ! grep -Fxq "$domain" "$current_sans"; then
    echo "Shared certificate is missing required SAN: $domain"
    needs_issue=true
  fi
done < "$required_sans"

if [ "$needs_issue" = true ]; then
  attempt=1
  issued=false

  while [ "$attempt" -le 5 ]; do
    set --
    while IFS= read -r domain; do
      if [ -n "$domain" ]; then
        set -- "$@" -d "$domain"
      fi
    done < "$required_sans"

    if edge_compose run --rm --no-deps --entrypoint certbot certbot \
      certonly --webroot -w /var/www/certbot \
      --cert-name ithute-edge --non-interactive --expand "$@"; then
      issued=true
      break
    fi

    echo "Shared certificate reconciliation attempt $attempt failed; retrying after DNS propagation."
    sleep 15
    attempt=$((attempt + 1))
  done

  if [ "$issued" != true ]; then
    echo "Could not reconcile the shared ithute-edge TLS certificate" >&2
    exit 1
  fi
fi

# Inspect the certificate from a fresh one-shot edge container. Do not depend
# on the already-running Nginx container after Certbot has atomically replaced
# certificate symlinks. Only restart the public listener after this complete
# SAN check succeeds.
cert_sans="$(edge_compose run --rm --no-deps --entrypoint /bin/sh edge-nginx -c \
  'command -v openssl >/dev/null 2>&1 || { echo "openssl is unavailable in edge image" >&2; exit 1; }; exec openssl x509 -in /etc/letsencrypt/live/ithute-edge/fullchain.pem -noout -ext subjectAltName')"
printf '%s\n' "$cert_sans"
while IFS= read -r domain; do
  [ -n "$domain" ] || continue
  printf '%s\n' "$cert_sans" | grep -Fq "DNS:$domain" || {
    echo "Reconciled certificate is still missing required SAN: $domain" >&2
    exit 1
  }
done < "$required_sans"

echo 'Canonical shared certificate SAN set verified before edge restart.'
edge_compose up -d --no-build --no-deps --force-recreate edge-nginx certbot
edge_compose exec -T edge-nginx nginx -t

# Shared TLS recovery must not depend on a single product being healthy. Verify
# the panel through the new local edge certificate; product-specific workflows
# keep their own application health gates.
attempt=1
while [ "$attempt" -le 30 ]; do
  if curl -fsS \
    --resolve "$health_host:443:127.0.0.1" \
    --connect-timeout 5 --max-time 15 \
    "https://$health_host/" >/dev/null; then
    echo "Shared HTTPS edge is healthy for $health_host."
    exit 0
  fi

  echo "Waiting for shared HTTPS edge ($health_host, $attempt/30)..."
  sleep 3
  attempt=$((attempt + 1))
done

edge_compose logs --tail=250 edge-nginx || true
echo "Shared HTTPS edge did not become healthy for $health_host." >&2
exit 1
