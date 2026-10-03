#!/usr/bin/env bash
set -euo pipefail

MAIL_DIR="${ITHUTE_MAIL_DIR:-/home/administrator/ithute-platform-mail}"
GATEWAY_DIR="${ITHUTE_GATEWAY_DIR:-$MAIL_DIR/gateway}"

test -f "$MAIL_DIR/compose.yml" || { echo "Missing $MAIL_DIR/compose.yml" >&2; exit 2; }
test -f "$GATEWAY_DIR/compose.yml" || { echo "Missing $GATEWAY_DIR/compose.yml" >&2; exit 2; }

echo "Moving routing gateway back to staging TCP/2525"
ITHUTE_GATEWAY_SMTP_BIND=2525 docker compose -p ithute-mail-gateway -f "$GATEWAY_DIR/compose.yml" up -d --force-recreate gateway

echo "Restoring existing Ithute Mail server to public TCP/25"
ITHUTE_MAIL_SMTP_BIND=25 docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" up -d --force-recreate mailserver

for _ in $(seq 1 45); do
  if docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' ithute-mail 2>/dev/null | grep -qx healthy; then
    rm -f "$MAIL_DIR/.ithute-routing-gateway-live"
    echo "Rollback complete. Ithute Mail owns public TCP/25 again."
    exit 0
  fi
  sleep 2
done

docker logs --tail=150 ithute-mail >&2 || true
echo "Rollback attempted but Ithute Mail did not become healthy." >&2
exit 1
