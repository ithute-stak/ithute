#!/usr/bin/env bash
set -euo pipefail

MAIL_DIR="${ITHUTE_MAIL_DIR:-/home/administrator/ithute-platform-mail}"
MAILSERVER_IMAGE="${ITHUTE_MAILSERVER_IMAGE:-ghcr.io/docker-mailserver/docker-mailserver:15.1.0}"
EXPECTED_MAP="texthash:/mail-accounts/postfix-recipient-bcc.cf"

if [ "$MAIL_DIR" = "/" ] || [ "$MAIL_DIR" = "/home" ] || [ "$MAIL_DIR" = "/home/administrator" ]; then
  echo "Unsafe Ithute mail directory: $MAIL_DIR" >&2
  exit 2
fi

test -f "$MAIL_DIR/.ithute-mail-finalized" || {
  echo "Ithute Mail must be finalized before inbound forwarding is enabled." >&2
  exit 2
}
test -f "$MAIL_DIR/compose.yml" || { echo "Missing $MAIL_DIR/compose.yml" >&2; exit 2; }
docker image inspect "$MAILSERVER_IMAGE" >/dev/null 2>&1 || {
  echo "Missing preloaded mail image: $MAILSERVER_IMAGE" >&2
  exit 4
}

mkdir -p "$MAIL_DIR/config" "$MAIL_DIR/accounts"

# Use the mail image as root for atomic configuration updates because Docker
# Mailserver may own files in the bind-mounted config directory. Existing
# unrelated Postfix overrides are retained; only recipient_bcc_maps is replaced.
docker run --rm --pull=never \
  -v "$MAIL_DIR/config:/dms-config" \
  -v "$MAIL_DIR/accounts:/mail-accounts" \
  --entrypoint /bin/sh \
  "$MAILSERVER_IMAGE" -c '
    set -eu
    main=/dms-config/postfix-main.cf
    forwarding=/mail-accounts/postfix-recipient-bcc.cf
    touch "$main" "$forwarding"
    chmod 600 "$main" "$forwarding"
    tmp=/dms-config/.postfix-main.forwarding
    awk '\''! /^[[:space:]]*recipient_bcc_maps[[:space:]]*=/'\'' "$main" > "$tmp"
    printf "\nrecipient_bcc_maps = texthash:/mail-accounts/postfix-recipient-bcc.cf\n" >> "$tmp"
    chmod 600 "$tmp"
    mv "$tmp" "$main"
  '

# Recreate only the mailserver container. Mail data/state remain on their
# persistent bind mounts, while Postfix receives the new immutable main.cf
# override. No mailbox credential is changed or exposed.
docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" up -d --pull never --force-recreate mailserver

health=""
for attempt in $(seq 1 45); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' ithute-mail 2>/dev/null || true)"
  [ "$health" = healthy ] && break
  if [ "$attempt" -eq 45 ]; then
    docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" logs --tail=200 mailserver >&2 || true
    echo "Mail container did not become healthy after recipient-copy configuration; last state: ${health:-missing}" >&2
    exit 1
  fi
  sleep 2
done

docker exec ithute-mail postconf -m | grep -Fxq texthash || {
  echo "Postfix does not expose the required texthash map type." >&2
  exit 1
}
actual_map="$(docker exec ithute-mail postconf -h recipient_bcc_maps | tr -d '\r')"
[ "$actual_map" = "$EXPECTED_MAP" ] || {
  echo "Unexpected recipient_bcc_maps value: $actual_map" >&2
  exit 1
}
docker exec ithute-mail test -f /mail-accounts/postfix-recipient-bcc.cf

# The application treats this marker as proof that Postfix has loaded the exact
# expected recipient-copy map. Create it only after all runtime checks pass.
docker run --rm --pull=never \
  -v "$MAIL_DIR/accounts:/mail-accounts" \
  --entrypoint /bin/sh \
  "$MAILSERVER_IMAGE" -c '
    set -eu
    touch /mail-accounts/.recipient-bcc-ready
    chmod 644 /mail-accounts/.recipient-bcc-ready
  '

echo "Ithute Mail inbound recipient-copy runtime is ready: $EXPECTED_MAP"
