#!/usr/bin/env bash
set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }
info() { echo "INFO: $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="${SCRIPT_DIR}/validate-host.sh"

[[ -x "$VALIDATOR" ]] || fail "Host validator is missing or not executable: $VALIDATOR"

# Final production acceptance is intentionally stricter than initial provisioning.
export ITHUTE_HOSTING_REQUIRE_AGENT_ACTIVE=true
"$VALIDATOR"

systemctl is-enabled --quiet ithute-hosting-egress.service || fail "ithute-hosting-egress.service is not enabled"
systemctl is-active --quiet ithute-hosting-egress.service || fail "ithute-hosting-egress.service is not active"
systemctl is-enabled --quiet ithute-hosting-agent.service || fail "ithute-hosting-agent.service is not enabled"
systemctl is-active --quiet ithute-hosting-agent.service || fail "ithute-hosting-agent.service is not active"
ok "Hosting firewall and agent services are enabled and active"

# Confirm Docker sees the protected jump after the daemon has started. Operators should
# run this script once normally and again after both a Docker restart and a host reboot.
NETWORK_POOL="${ITHUTE_HOSTING_NETWORK_POOL:-10.240.0.0/12}"
iptables -C DOCKER-USER -s "$NETWORK_POOL" -j ITHUTE-HOSTING-EGRESS >/dev/null 2>&1 || \
  fail "DOCKER-USER no longer routes the reserved hosting pool through ITHUTE-HOSTING-EGRESS"
ok "Hosted network pool remains attached to the egress policy"

# Optional public ingress probe. Set this to a disposable verified customer hostname
# that is currently routed through Ithute Caddy to a healthy hosted application.
if [[ -n "${ITHUTE_HOSTING_SMOKE_DOMAIN:-}" ]]; then
  command -v curl >/dev/null 2>&1 || fail "curl is required for ITHUTE_HOSTING_SMOKE_DOMAIN"
  url="https://${ITHUTE_HOSTING_SMOKE_DOMAIN}/"
  status="$(curl --silent --show-error --location --output /dev/null --write-out '%{http_code}' \
    --connect-timeout 10 --max-time 30 "$url")"
  [[ "$status" =~ ^2|3[0-9][0-9]$ ]] || fail "Public ingress probe returned HTTP $status for $url"
  ok "Public ingress probe succeeded for $url (HTTP $status)"
else
  info "ITHUTE_HOSTING_SMOKE_DOMAIN is unset; public customer-domain ingress probe skipped"
fi

# Optional container-health probe for the same disposable acceptance application.
if [[ -n "${ITHUTE_HOSTING_SMOKE_CONTAINER:-}" ]]; then
  state="$(docker inspect --format '{{.State.Status}}' "$ITHUTE_HOSTING_SMOKE_CONTAINER" 2>/dev/null || true)"
  [[ "$state" == "running" ]] || fail "Acceptance container is not running: ${ITHUTE_HOSTING_SMOKE_CONTAINER} (state=${state:-missing})"
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$ITHUTE_HOSTING_SMOKE_CONTAINER")"
  [[ "$health" == "healthy" || "$health" == "none" ]] || fail "Acceptance container health is $health"
  ok "Acceptance container is running (health=$health)"
else
  info "ITHUTE_HOSTING_SMOKE_CONTAINER is unset; container-health probe skipped"
fi

# Optional off-node storage reachability. This is deliberately read-only and does not
# replace the required destructive node-loss/rehydration drill documented in README.md.
if [[ -n "${ITHUTE_HOSTING_BACKUP_REMOTE:-}" ]]; then
  command -v rclone >/dev/null 2>&1 || fail "rclone is required when ITHUTE_HOSTING_BACKUP_REMOTE is configured"
  RCLONE_CONFIG="${ITHUTE_HOSTING_RCLONE_CONFIG:-/etc/ithute-hosting-node/rclone.conf}"
  [[ -r "$RCLONE_CONFIG" ]] || fail "rclone config is not readable: $RCLONE_CONFIG"
  rclone --config "$RCLONE_CONFIG" lsf "$ITHUTE_HOSTING_BACKUP_REMOTE" --max-depth 1 >/dev/null || \
    fail "Unable to read configured off-node backup destination"
  ok "Off-node backup destination is reachable"
else
  fail "ITHUTE_HOSTING_BACKUP_REMOTE must be configured for production acceptance"
fi

echo
echo "Production hosting-node acceptance passed."
echo "Run this command again after:"
echo "  1. systemctl restart docker"
echo "  2. a full host reboot"
echo "Then complete the documented disposable DB backup -> local-delete -> remote-rehydrate restore drill."
