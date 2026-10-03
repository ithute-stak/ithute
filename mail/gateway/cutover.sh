#!/usr/bin/env bash
set -euo pipefail

MAIL_DIR="${ITHUTE_MAIL_DIR:-/home/administrator/ithute-platform-mail}"
GATEWAY_DIR="${ITHUTE_GATEWAY_DIR:-$MAIL_DIR/gateway}"
ROUTING_DIR="${ITHUTE_MAIL_ROUTING_DIR:-$MAIL_DIR/routing}"
INTERNAL_SMTP_BIND="${ITHUTE_INTERNAL_SMTP_BIND:-127.0.0.1:2526}"

require() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 2; }; }
require docker
require ss

test -f "$MAIL_DIR/compose.yml" || { echo "Missing $MAIL_DIR/compose.yml" >&2; exit 2; }
test -f "$GATEWAY_DIR/compose.yml" || { echo "Missing $GATEWAY_DIR/compose.yml" >&2; exit 2; }
test -f "$ROUTING_DIR/.ready" || { echo "Routing maps have not been reconciled." >&2; exit 2; }

if [ -f "$MAIL_DIR/.ithute-routing-gateway-live" ]; then
  echo "Ithute routing gateway is already marked live."
  exit 0
fi

echo "[1/5] Starting gateway staging listener on host TCP/2525"
ITHUTE_GATEWAY_SMTP_BIND=2525 docker compose -p ithute-mail-gateway -f "$GATEWAY_DIR/compose.yml" up -d --build gateway

for _ in $(seq 1 30); do
  if docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' ithute-mail-gateway 2>/dev/null | grep -qx healthy; then
    break
  fi
  sleep 2
done
docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' ithute-mail-gateway | grep -qx healthy || {
  docker logs --tail=150 ithute-mail-gateway >&2 || true
  echo "Gateway staging health check failed." >&2
  exit 1
}
ss -ltn | grep -Eq '[:.]2525[[:space:]]' || { echo "Gateway is not listening on host TCP/2525." >&2; exit 1; }

echo "[2/5] Verifying gateway routing maps"
docker exec ithute-mail-gateway postconf -h relay_domains | grep -Fq '/routing/relay-domains.cf'
docker exec ithute-mail-gateway postconf -h relay_recipient_maps | grep -Fq '/routing/relay-recipients.cf'
docker exec ithute-mail-gateway postconf -h transport_maps | grep -Fq '/routing/transport.cf'

echo "[3/5] Moving the internal mailbox server away from public TCP/25"
ITHUTE_MAIL_SMTP_BIND="$INTERNAL_SMTP_BIND" docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" up -d --force-recreate mailserver

for _ in $(seq 1 45); do
  if docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' ithute-mail 2>/dev/null | grep -qx healthy; then
    break
  fi
  sleep 2
done
docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' ithute-mail | grep -qx healthy || {
  echo "Internal mailserver did not recover after SMTP port handoff; restoring public TCP/25." >&2
  ITHUTE_GATEWAY_SMTP_BIND=2525 docker compose -p ithute-mail-gateway -f "$GATEWAY_DIR/compose.yml" up -d gateway || true
  ITHUTE_MAIL_SMTP_BIND=25 docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" up -d --force-recreate mailserver || true
  exit 1
}

echo "[4/5] Promoting routing gateway to public TCP/25"
ITHUTE_GATEWAY_SMTP_BIND=25 docker compose -p ithute-mail-gateway -f "$GATEWAY_DIR/compose.yml" up -d --force-recreate gateway

for _ in $(seq 1 30); do
  if docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' ithute-mail-gateway 2>/dev/null | grep -qx healthy; then
    break
  fi
  sleep 2
done
if ! docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' ithute-mail-gateway | grep -qx healthy; then
  echo "Gateway failed after public promotion; rolling back." >&2
  ITHUTE_GATEWAY_SMTP_BIND=2525 docker compose -p ithute-mail-gateway -f "$GATEWAY_DIR/compose.yml" up -d --force-recreate gateway || true
  ITHUTE_MAIL_SMTP_BIND=25 docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" up -d --force-recreate mailserver || true
  exit 1
fi
ss -ltn | grep -Eq '[:.]25[[:space:]]' || {
  echo "Nothing is listening on public TCP/25 after gateway promotion; rolling back." >&2
  ITHUTE_GATEWAY_SMTP_BIND=2525 docker compose -p ithute-mail-gateway -f "$GATEWAY_DIR/compose.yml" up -d --force-recreate gateway || true
  ITHUTE_MAIL_SMTP_BIND=25 docker compose -p ithute-mail -f "$MAIL_DIR/compose.yml" up -d --force-recreate mailserver || true
  exit 1
}

echo "[5/5] Recording successful gateway cutover"
cat > "$MAIL_DIR/.ithute-routing-gateway-live" <<EOF
cutover_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
internal_smtp_bind=$INTERNAL_SMTP_BIND
gateway_public_port=25
EOF
chmod 0644 "$MAIL_DIR/.ithute-routing-gateway-live"
echo "Ithute routing gateway is live on public TCP/25. Submission 465/587 and IMAPS 993 remain on the mailbox server."
