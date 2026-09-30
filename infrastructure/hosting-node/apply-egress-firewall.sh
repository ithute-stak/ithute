#!/usr/bin/env bash
set -euo pipefail

# Apply a deliberately narrow egress policy only to Docker networks created by
# the Ithute hosting agent (label ithute.hosted=true). This script does not
# flush or replace the host INPUT/FORWARD firewall and never runs docker prune.

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root so DOCKER-USER rules can be managed." >&2
  exit 1
fi

for binary in docker iptables; do
  command -v "$binary" >/dev/null 2>&1 || { echo "Missing required command: $binary" >&2; exit 1; }
done

docker info >/dev/null
iptables -S DOCKER-USER >/dev/null 2>&1 || {
  echo "Docker DOCKER-USER chain is unavailable; refusing to modify firewall." >&2
  exit 1
}

CHAIN="ITHUTE-HOSTING-EGRESS"
DB_GATEWAY_IP="${ITHUTE_HOSTING_DB_GATEWAY_IP:-$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)}"
ALLOW_HTTP="${ITHUTE_HOSTING_EGRESS_ALLOW_HTTP:-true}"
ALLOW_HTTPS="${ITHUTE_HOSTING_EGRESS_ALLOW_HTTPS:-true}"
ALLOW_DNS="${ITHUTE_HOSTING_EGRESS_ALLOW_DNS:-true}"
POSTGRES_PORT="${ITHUTE_HOSTING_POSTGRES_PORT:-5432}"
MYSQL_PORT="${ITHUTE_HOSTING_MYSQL_PORT:-3306}"

if [[ -z "$DB_GATEWAY_IP" ]]; then
  echo "Unable to resolve Docker host gateway. Set ITHUTE_HOSTING_DB_GATEWAY_IP explicitly." >&2
  exit 1
fi

python3 - "$DB_GATEWAY_IP" <<'PY'
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
if not (ip.is_private or ip.is_loopback):
    raise SystemExit("Refusing public ITHUTE_HOSTING_DB_GATEWAY_IP")
PY

if ! iptables -S "$CHAIN" >/dev/null 2>&1; then
  iptables -N "$CHAIN"
fi
iptables -F "$CHAIN"

# Return traffic from permitted outbound connections.
iptables -A "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Project-scoped database access reaches only the host gateway and configured DB ports.
iptables -A "$CHAIN" -d "$DB_GATEWAY_IP/32" -p tcp --dport "$POSTGRES_PORT" -j ACCEPT
iptables -A "$CHAIN" -d "$DB_GATEWAY_IP/32" -p tcp --dport "$MYSQL_PORT" -j ACCEPT

# Block cloud metadata, loopback, link-local and private east/west access before
# permitting ordinary Internet web traffic. The database gateway exception above
# is intentionally evaluated first.
for cidr in \
  0.0.0.0/8 \
  10.0.0.0/8 \
  100.64.0.0/10 \
  127.0.0.0/8 \
  169.254.0.0/16 \
  172.16.0.0/12 \
  192.0.0.0/24 \
  192.168.0.0/16 \
  198.18.0.0/15 \
  224.0.0.0/4 \
  240.0.0.0/4; do
  iptables -A "$CHAIN" -d "$cidr" -j REJECT --reject-with icmp-port-unreachable
done

if [[ "$ALLOW_DNS" == "true" ]]; then
  iptables -A "$CHAIN" -p udp --dport 53 -j ACCEPT
  iptables -A "$CHAIN" -p tcp --dport 53 -j ACCEPT
fi
if [[ "$ALLOW_HTTP" == "true" ]]; then
  iptables -A "$CHAIN" -p tcp --dport 80 -j ACCEPT
fi
if [[ "$ALLOW_HTTPS" == "true" ]]; then
  iptables -A "$CHAIN" -p tcp --dport 443 -j ACCEPT
fi

# Everything else from a hosted project network is denied by default. This
# prevents direct SMTP, SSH, database scanning and arbitrary lateral movement.
iptables -A "$CHAIN" -j REJECT --reject-with icmp-port-unreachable

mapfile -t NETWORKS < <(docker network ls --filter label=ithute.hosted=true --format '{{.ID}}')
for network_id in "${NETWORKS[@]}"; do
  [[ -n "$network_id" ]] || continue
  subnet="$(docker network inspect "$network_id" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}')"
  [[ -n "$subnet" ]] || { echo "Hosted network $network_id has no IPv4 subnet; refusing partial policy." >&2; exit 1; }

  # Remove stale duplicate jumps for this exact source subnet, then insert the
  # scoped jump before Docker's normal forwarding acceptance.
  while iptables -C DOCKER-USER -s "$subnet" -j "$CHAIN" 2>/dev/null; do
    iptables -D DOCKER-USER -s "$subnet" -j "$CHAIN"
  done
  iptables -I DOCKER-USER 1 -s "$subnet" -j "$CHAIN"
  echo "Protected hosted network $network_id ($subnet)"
done

echo "Ithute hosted-workload egress policy active. DB gateway: $DB_GATEWAY_IP"
