#!/usr/bin/env sh
set -eu

: "${MAILBOX_APP_DIR:?MAILBOX_APP_DIR is required}"
: "${PLATFORM_DOMAIN:=ithute.co.ls}"
: "${PUBLIC_IP:?PUBLIC_IP is required}"

cd "$MAILBOX_APP_DIR"
[ -s .env ] || { echo "Mailbox-DNS production .env is missing" >&2; exit 1; }

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml -f docker-compose.phase12-monitoring.yml -f docker-compose.ithute-platform.yml -f docker-compose.deploy.yml"
if grep -q '^HA_MAIL_ENABLED=true$' .env; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.ha-mail.yml -f docker-compose.deploy-ha.yml"
fi

compose() {
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES "$@"
}

compose exec -T \
  -e PLATFORM_DOMAIN="$PLATFORM_DOMAIN" \
  -e PUBLIC_IP="$PUBLIC_IP" \
  backend python - <<'PY'
import os

from app.services.powerdns import PowerDNSClient

zone = os.environ["PLATFORM_DOMAIN"].strip().rstrip(".").lower()
public_ip = os.environ["PUBLIC_IP"].strip()
client = PowerDNSClient()

hosts = (
    zone,
    f"www.{zone}",
    f"panel.{zone}",
    f"api.{zone}",
    f"auth.{zone}",
    f"push.{zone}",
    f"realtime.{zone}",
    f"tutor.{zone}",
    f"groupware.{zone}",
    f"pay.{zone}",
    f"api.pay.{zone}",
    f"portal.pay.{zone}",
    f"mail.{zone}",
)

for hostname in hosts:
    client.replace_rrset(zone, hostname, "A", 3600, [public_ip])
client.replace_rrset(zone, zone, "CAA", 3600, ['0 issue "letsencrypt.org"'])
client.rectify_zone(zone)
print(f"Reconciled {len(hosts)} Nginx edge hostnames for {zone} -> {public_ip}")
PY

for host in \
  "$PLATFORM_DOMAIN" \
  "www.$PLATFORM_DOMAIN" \
  "panel.$PLATFORM_DOMAIN" \
  "api.$PLATFORM_DOMAIN" \
  "auth.$PLATFORM_DOMAIN" \
  "push.$PLATFORM_DOMAIN" \
  "realtime.$PLATFORM_DOMAIN" \
  "tutor.$PLATFORM_DOMAIN" \
  "groupware.$PLATFORM_DOMAIN" \
  "pay.$PLATFORM_DOMAIN" \
  "api.pay.$PLATFORM_DOMAIN" \
  "portal.pay.$PLATFORM_DOMAIN" \
  "mail.$PLATFORM_DOMAIN"; do
  dig +short @"$PUBLIC_IP" "$host" A | grep -Fx "$PUBLIC_IP" >/dev/null || {
    echo "Authoritative DNS verification failed for $host" >&2
    exit 1
  }
done

echo "Nginx edge DNS reconciliation completed successfully."
