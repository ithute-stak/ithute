#!/usr/bin/env sh
set -eu

[ -f .env ] || { echo "Missing production .env in $(pwd)" >&2; exit 1; }

PLATFORM_DOMAIN="${PLATFORM_DOMAIN:-ithute.co.ls}"
PUBLIC_IP="${PUBLIC_IP:-204.12.205.224}"

case "$PLATFORM_DOMAIN" in
  *.*) ;;
  *) echo "PLATFORM_DOMAIN must be a fully-qualified domain name" >&2; exit 1 ;;
esac
case "$PLATFORM_DOMAIN" in
  *.example|*.example.*|*.test|*.test.*|*.invalid|*.invalid.*)
    echo "Refusing placeholder/test platform domain: $PLATFORM_DOMAIN" >&2
    exit 1
    ;;
esac

NS1="ns1.${PLATFORM_DOMAIN}"
NS2="ns2.${PLATFORM_DOMAIN}"
MAIL_HOST="mail.${PLATFORM_DOMAIN}"
# PANEL_HOSTNAME is retained only as a compatibility setting. The public
# frontend is the apex itself; panel.<domain> is deliberately retired.
PANEL_HOST="$PLATFORM_DOMAIN"
API_HOST="api.${PLATFORM_DOMAIN}"
AUTH_HOST="auth.${PLATFORM_DOMAIN}"
PUSH_HOST="push.${PLATFORM_DOMAIN}"
REALTIME_HOST="realtime.${PLATFORM_DOMAIN}"
GROUPWARE_HOST="groupware.${PLATFORM_DOMAIN}"
WWW_HOST="www.${PLATFORM_DOMAIN}"

upsert_env() {
  key="$1"
  value="$2"
  tmp="$(mktemp)"
  awk -v k="$key" 'index($0, k "=") != 1 { print }' .env > "$tmp"
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
}

# Persist the real public DNS/mail identity while remaining in bootstrap mode.
# The backend deliberately refuses PLATFORM_MODE=domain until HTTPS, secure
# cookies, non-self-signed mail TLS, system SMTP and HTTPS groupware are ready.
upsert_env PLATFORM_MODE bootstrap
upsert_env NAMESERVER_1 "$NS1"
upsert_env NAMESERVER_2 "$NS2"
upsert_env MAIL_HOSTNAME "$MAIL_HOST"
upsert_env PANEL_HOSTNAME "$PANEL_HOST"
upsert_env FRONTEND_URL "https://${PLATFORM_DOMAIN}"
upsert_env ITHUTE_AUTH_CORS_ORIGINS "https://${PLATFORM_DOMAIN}"
upsert_env API_HOSTNAME "$API_HOST"
upsert_env GROUPWARE_HOSTNAME "$GROUPWARE_HOST"
chmod 600 .env

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml -f docker-compose.phase12-monitoring.yml -f docker-compose.ithute-platform.yml -f docker-compose.deploy.yml"
if grep -q '^HA_MAIL_ENABLED=true$' .env; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.ha-mail.yml -f docker-compose.deploy-ha.yml"
fi

compose() {
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES "$@"
}

wait_service() {
  service="$1"
  max_attempts="${2:-90}"
  id="$(compose ps -q "$service")"
  [ -n "$id" ] || { echo "Service $service has no container" >&2; return 1; }
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || true)"
    case "$status" in
      healthy|running) return 0 ;;
      exited|dead|unhealthy)
        echo "Service $service entered $status" >&2
        compose logs --tail=200 "$service" >&2 || true
        return 1
        ;;
    esac
    sleep 2
    attempt=$((attempt + 1))
  done
  echo "Timed out waiting for $service" >&2
  compose logs --tail=200 "$service" >&2 || true
  return 1
}

compose config >/dev/null

# Recreate only services that consume platform/mail identity. --no-deps keeps
# PostgreSQL/Redis/PowerDNS data services untouched. Nginx is recreated after
# backend so its Docker DNS upstream cannot become stale.
compose up -d --no-deps --no-build --pull never --force-recreate backend
wait_service backend
compose up -d --no-deps --no-build --pull never --force-recreate postfix dovecot smtp-policy
wait_service postfix
wait_service dovecot
wait_service smtp-policy
compose up -d --no-deps --no-build --pull never --force-recreate nginx
wait_service nginx

# Reconcile the platform's already-delegated authoritative zone. This fixes the
# PowerDNS fallback SOA MNAME and creates the complete public identity required
# by the shared HTTPS edge and mail clients. The retired panel hostname is
# explicitly removed so it cannot be recreated by later reconciliation runs.
compose exec -T \
  -e PLATFORM_DOMAIN="$PLATFORM_DOMAIN" \
  -e PUBLIC_IP="$PUBLIC_IP" \
  backend python - <<'PY'
import os

from app.services.powerdns import PowerDNSClient, PowerDNSError

zone = os.environ["PLATFORM_DOMAIN"].strip().rstrip(".").lower()
public_ip = os.environ["PUBLIC_IP"].strip()
ns1 = f"ns1.{zone}"
ns2 = f"ns2.{zone}"
mail = f"mail.{zone}"
legacy_panel = f"panel.{zone}"
api = f"api.{zone}"
auth = f"auth.{zone}"
push = f"push.{zone}"
realtime = f"realtime.{zone}"
groupware = f"groupware.{zone}"
www = f"www.{zone}"
client = PowerDNSClient()

try:
    client.get_zone(zone)
except PowerDNSError as exc:
    if exc.status_code != 404 and "HTTP 404" not in str(exc):
        raise
    client.create_zone_with_nameservers(zone, [ns1, ns2])

client.reconcile_authority(zone, [ns1, ns2])
for hostname in (zone, www, api, auth, push, realtime, groupware, ns1, ns2, mail):
    client.replace_rrset(zone, hostname, "A", 3600, [public_ip])
for record_type in ("A", "AAAA", "CNAME"):
    client.delete_rrset(zone, legacy_panel, record_type)
client.replace_rrset(zone, zone, "MX", 3600, [f"10 {mail}."])
client.replace_rrset(zone, zone, "TXT", 3600, ['"v=spf1 mx -all"'])
client.replace_rrset(zone, f"_dmarc.{zone}", "TXT", 3600, [f'"v=DMARC1; p=quarantine; rua=mailto:dmarc@{zone}; adkim=s; aspf=s"'])
client.replace_rrset(zone, zone, "CAA", 3600, ['0 issue "letsencrypt.org"'])
client.replace_rrset(zone, f"_submission._tcp.{zone}", "SRV", 3600, [f"0 1 587 {mail}."])
client.replace_rrset(zone, f"_imaps._tcp.{zone}", "SRV", 3600, [f"0 1 993 {mail}."])
client.rectify_zone(zone)
print(f"Reconciled authoritative identity for {zone}; retired {legacy_panel}")
PY

command -v dig >/dev/null 2>&1 || { echo "dig is required on the production VPS" >&2; exit 1; }

soa="$(dig +short @"$PUBLIC_IP" "$PLATFORM_DOMAIN" SOA)"
set -- $soa
[ "${1:-}" = "${NS1}." ] || { echo "Unexpected SOA primary: ${1:-missing}" >&2; exit 1; }
[ "${2:-}" = "hostmaster.${PLATFORM_DOMAIN}." ] || { echo "Unexpected SOA hostmaster: ${2:-missing}" >&2; exit 1; }

ns="$(dig +short @"$PUBLIC_IP" "$PLATFORM_DOMAIN" NS | sort)"
printf '%s\n' "$ns" | grep -Fx "${NS1}." >/dev/null
printf '%s\n' "$ns" | grep -Fx "${NS2}." >/dev/null

for host in "$PLATFORM_DOMAIN" "$WWW_HOST" "$API_HOST" "$AUTH_HOST" "$PUSH_HOST" "$REALTIME_HOST" "$GROUPWARE_HOST" "$NS1" "$NS2" "$MAIL_HOST"; do
  dig +short @"$PUBLIC_IP" "$host" A | grep -Fx "$PUBLIC_IP" >/dev/null
done

if [ -n "$(dig +short @"$PUBLIC_IP" "panel.${PLATFORM_DOMAIN}" A)" ] || \
   [ -n "$(dig +short @"$PUBLIC_IP" "panel.${PLATFORM_DOMAIN}" AAAA)" ] || \
   [ -n "$(dig +short @"$PUBLIC_IP" "panel.${PLATFORM_DOMAIN}" CNAME)" ]; then
  echo "Retired panel.${PLATFORM_DOMAIN} still resolves" >&2
  exit 1
fi

mx="$(dig +short @"$PUBLIC_IP" "$PLATFORM_DOMAIN" MX)"
set -- $mx
[ "${1:-}" = "10" ] || { echo "Unexpected MX preference: ${1:-missing}" >&2; exit 1; }
[ "${2:-}" = "${MAIL_HOST}." ] || { echo "Unexpected MX target: ${2:-missing}" >&2; exit 1; }

dig +short @"$PUBLIC_IP" "$PLATFORM_DOMAIN" TXT | grep -F 'v=spf1 mx -all' >/dev/null
dig +short @"$PUBLIC_IP" "_dmarc.${PLATFORM_DOMAIN}" TXT | grep -F 'v=DMARC1; p=quarantine' >/dev/null

tcp_soa="$(dig +tcp +short @"$PUBLIC_IP" "$PLATFORM_DOMAIN" SOA)"
set -- $tcp_soa
[ "${1:-}" = "${NS1}." ] || { echo "TCP DNS returned unexpected SOA primary: ${1:-missing}" >&2; exit 1; }

recursion_status="$(dig @"$PUBLIC_IP" example.net A +time=3 +tries=1 2>/dev/null | sed -n 's/.*status: \([A-Z]*\),.*/\1/p' | head -n1)"
case "$recursion_status" in
  REFUSED|SERVFAIL) ;;
  *) echo "Authoritative DNS recursion check returned unexpected status: ${recursion_status:-unknown}" >&2; exit 1 ;;
esac

# Populate the platform-setup control-plane record from the verified public
# identity. This records domain_verified, never domain_active: hardened
# activation still has its own MFA/HTTPS/TLS prerequisites.
compose exec -T \
  -e PLATFORM_DOMAIN="$PLATFORM_DOMAIN" \
  -e PUBLIC_IP="$PUBLIC_IP" \
  backend python - <<'PY'
import os
from datetime import datetime, timezone

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import PlatformConfiguration
from app.services.platform_setup import platform_names, verify_public_delegation

zone = os.environ["PLATFORM_DOMAIN"].strip().rstrip(".").lower()
public_ip = os.environ["PUBLIC_IP"].strip()
names = platform_names(zone)
verification = verify_public_delegation(names, public_ip, public_ip)
now = datetime.now(timezone.utc)

with SessionLocal() as db:
    row = db.get(PlatformConfiguration, 1)
    if row is None:
        row = PlatformConfiguration(id=1, bootstrap_public_ip=public_ip, mode="bootstrap", security_level="bootstrap")
        db.add(row)
    row.bootstrap_public_ip = public_ip
    row.primary_domain = zone
    row.panel_hostname = names.panel
    row.api_hostname = names.api
    row.groupware_hostname = names.groupware
    row.mail_hostname = names.mail
    row.nameserver_1 = names.ns1
    row.nameserver_2 = names.ns2
    row.nameserver_1_ip = public_ip
    row.nameserver_2_ip = public_ip
    row.acme_email = settings.bootstrap_admin_email.strip().lower()
    row.dns_zone_provisioned_at = row.dns_zone_provisioned_at or now
    if verification["verified"]:
        row.mode = "domain_verified"
        row.delegation_verified_at = row.delegation_verified_at or now
    else:
        row.mode = "domain_pending"
        row.delegation_verified_at = None
    row.security_level = "bootstrap"
    db.commit()
print(f"Platform setup state: {'domain_verified' if verification['verified'] else 'domain_pending'}")
PY

printf '\nProduction DNS/mail identity enforced in bootstrap-safe mode.\n'
printf 'Platform domain: %s\n' "$PLATFORM_DOMAIN"
printf 'Frontend: https://%s\n' "$PLATFORM_DOMAIN"
printf 'Nameservers: %s, %s\n' "$NS1" "$NS2"
printf 'Mail hostname: %s\n' "$MAIL_HOST"
printf 'Public IP: %s\n' "$PUBLIC_IP"
printf 'Platform mode remains bootstrap until HTTPS/mail TLS prerequisites pass.\n'