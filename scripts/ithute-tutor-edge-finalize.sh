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

san_file="$(mktemp)"
cleanup() {
  rm -f "$san_file"
}
trap cleanup EXIT HUP INT TERM

# Read the current shared certificate SANs. Existing names are preserved when
# Tutor is added, so this operation cannot replace the shared certificate with
# a Tutor-only certificate.
edge_compose exec -T edge-nginx openssl x509 \
  -in /etc/letsencrypt/live/ithute-edge/fullchain.pem \
  -noout -ext subjectAltName \
  | tr ',' '\n' \
  | sed -n 's/^[[:space:]]*DNS://p' \
  | sed 's/[[:space:]]//g' \
  | sed '/^$/d' > "$san_file"

if ! grep -Fxq "$TUTOR_HOST" "$san_file"; then
  printf '%s\n' "$TUTOR_HOST" >> "$san_file"
  attempt=1
  issued=false

  while [ "$attempt" -le 5 ]; do
    set --
    while IFS= read -r domain; do
      if [ -n "$domain" ]; then
        set -- "$@" -d "$domain"
      fi
    done < "$san_file"

    if edge_compose run --rm --no-deps --entrypoint certbot certbot \
      certonly --webroot -w /var/www/certbot \
      --cert-name ithute-edge --non-interactive --expand "$@"; then
      issued=true
      break
    fi

    echo "Tutor certificate expansion attempt $attempt failed; retrying after DNS propagation."
    sleep 15
    attempt=$((attempt + 1))
  done

  if [ "$issued" != true ]; then
    echo "Could not extend ithute-edge TLS certificate for Tutor" >&2
    exit 1
  fi
fi

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
