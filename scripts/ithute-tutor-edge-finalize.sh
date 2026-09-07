#!/usr/bin/env sh
set -eu

: "${EDGE_DIR:?EDGE_DIR is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${TUTOR_HOST:?TUTOR_HOST is required}"

staged_template="${TUTOR_EDGE_TEMPLATE:-/tmp/ithute-edge-tutor-${DEPLOY_SHA}.conf}"
live_template="$EDGE_DIR/infrastructure/ithute-edge/default.conf.template"

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

# Read the certificate currently mounted into the edge only for comparison.
# It is deliberately not used as the authoritative domain list.
edge_compose exec -T edge-nginx openssl x509 \
  -in /etc/letsencrypt/live/ithute-edge/fullchain.pem \
  -noout -ext subjectAltName \
  | tr ',' '\n' \
  | sed -n 's/^[[:space:]]*DNS://p' \
  | sed 's/[[:space:]]//g' \
  | sed '/^$/d' > "$current_sans"

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

# Refuse to restart the edge with a certificate that does not cover every
# configured public hostname. This prevents one product deployment from
# silently breaking Panel, Auth, Pay, Tutor, or LoanHub TLS.
cert_sans="$(edge_compose exec -T edge-nginx openssl x509 \
  -in /etc/letsencrypt/live/ithute-edge/fullchain.pem \
  -noout -ext subjectAltName)"
printf '%s\n' "$cert_sans"
while IFS= read -r domain; do
  [ -n "$domain" ] || continue
  printf '%s\n' "$cert_sans" | grep -Fq "DNS:$domain" || {
    echo "Reconciled certificate is still missing required SAN: $domain" >&2
    exit 1
  }
done < "$required_sans"

edge_compose up -d --no-build --no-deps --force-recreate edge-nginx certbot
edge_compose exec -T edge-nginx nginx -t

attempt=1
while [ "$attempt" -le 30 ]; do
  if curl -fsS \
    --resolve "$TUTOR_HOST:443:127.0.0.1" \
    --connect-timeout 5 --max-time 15 \
    "https://$TUTOR_HOST/" >/dev/null; then
    echo "Tutor origin is healthy through the shared HTTPS edge."
    exit 0
  fi

  echo "Waiting for Tutor HTTPS origin ($attempt/30)..."
  sleep 3
  attempt=$((attempt + 1))
done

edge_compose logs --tail=250 edge-nginx || true
echo "Tutor HTTPS origin did not become healthy." >&2
exit 1
