#!/usr/bin/env bash
set -euo pipefail

# Apply a deliberately narrow egress policy only to the reserved CIDR used by
# Ithute hosted project networks. The source-pool jump exists before any project
# network/container starts, eliminating a network-creation race. This script
# never flushes the host INPUT/FORWARD firewall and never runs docker prune.

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root so DOCKER-USER rules can be managed." >&2
  exit 1
fi

for binary in docker iptables python3; do
  command -v "$binary" >/dev/null 2>&1 || { echo "Missing required command: $binary" >&2; exit 1; }
done

docker info >/dev/null
iptables -S DOCKER-USER >/dev/null 2>&1 || {
  echo "Docker DOCKER-USER chain is unavailable; refusing to modify firewall." >&2
  exit 1
}

CHAIN="ITHUTE-HOSTING-EGRESS"
NETWORK_POOL="${ITHUTE_HOSTING_NETWORK_POOL:-10.240.0.0/12}"
NETWORK_PREFIX="${ITHUTE_HOSTING_NETWORK_PREFIX:-28}"
DB_GATEWAY_IP="${ITHUTE_HOSTING_DB_GATEWAY_IP:-$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)}"
ALLOW_HTTP="${ITHUTE_HOSTING_EGRESS_ALLOW_HTTP:-true}"
ALLOW_HTTPS="${ITHUTE_HOSTING_EGRESS_ALLOW_HTTPS:-true}"
ALLOW_DNS="${ITHUTE_HOSTING_EGRESS_ALLOW_DNS:-true}"
POSTGRES_PORT="${ITHUTE_HOSTING_POSTGRES_PORT:-5432}"
MYSQL_PORT="${ITHUTE_HOSTING_MYSQL_PORT:-3306}"
ORIGIN_BIND_IP="${ITHUTE_HOSTING_ORIGIN_BIND_IP:-}"
ORIGIN_PORT_START="${ITHUTE_HOSTING_ORIGIN_PORT_START:-22000}"
ORIGIN_PORT_END="${ITHUTE_HOSTING_ORIGIN_PORT_END:-29999}"
EDGE_ORIGIN_CIDRS="${ITHUTE_EDGE_ORIGIN_CIDRS:-}"
INGRESS_CHAIN="ITHUTE-HOSTING-INGRESS"

if [[ -z "$DB_GATEWAY_IP" ]]; then
  echo "Unable to resolve Docker host gateway. Set ITHUTE_HOSTING_DB_GATEWAY_IP explicitly." >&2
  exit 1
fi

if [[ -n "$ORIGIN_BIND_IP" ]]; then
  [[ -n "$EDGE_ORIGIN_CIDRS" ]] || { echo "ITHUTE_EDGE_ORIGIN_CIDRS is required when private origin handoff is enabled." >&2; exit 1; }
  python3 - "$ORIGIN_BIND_IP" "$ORIGIN_PORT_START" "$ORIGIN_PORT_END" "$EDGE_ORIGIN_CIDRS" <<'PY'
import ipaddress, sys
address = ipaddress.ip_address(sys.argv[1])
start = int(sys.argv[2]); end = int(sys.argv[3])
if not address.is_private or address.is_unspecified or address.is_multicast or address.is_link_local:
    raise SystemExit("ITHUTE_HOSTING_ORIGIN_BIND_IP must be a private/VPN address")
if not (1024 <= start <= end <= 65535):
    raise SystemExit("Private origin port range is invalid")
for item in [x.strip() for x in sys.argv[4].split(",") if x.strip()]:
    ipaddress.ip_network(item, strict=False)
PY
fi

python3 - "$DB_GATEWAY_IP" "$NETWORK_POOL" "$NETWORK_PREFIX" <<'PY'
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
pool = ipaddress.ip_network(sys.argv[2], strict=True)
prefix = int(sys.argv[3])
if not (ip.is_private or ip.is_loopback):
    raise SystemExit("Refusing public ITHUTE_HOSTING_DB_GATEWAY_IP")
if not isinstance(pool, ipaddress.IPv4Network) or not pool.is_private:
    raise SystemExit("ITHUTE_HOSTING_NETWORK_POOL must be a private IPv4 CIDR")
if prefix < pool.prefixlen or prefix > 28:
    raise SystemExit("ITHUTE_HOSTING_NETWORK_PREFIX must be between the pool prefix and /28")
PY

# Refuse to reserve a pool already consumed by unrelated Docker networks. This
# keeps the source CIDR safe to match as "Ithute hosted only" in DOCKER-USER.
mapfile -t ALL_NETWORKS < <(docker network ls --format '{{.ID}}')
for network_id in "${ALL_NETWORKS[@]}"; do
  [[ -n "$network_id" ]] || continue
  hosted="$(docker network inspect "$network_id" --format '{{index .Labels "ithute.hosted"}}' 2>/dev/null || true)"
  mapfile -t subnets < <(docker network inspect "$network_id" --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' 2>/dev/null || true)
  for subnet in "${subnets[@]}"; do
    [[ -n "$subnet" ]] || continue
    if python3 - "$NETWORK_POOL" "$subnet" <<'PY'
import ipaddress, sys
pool = ipaddress.ip_network(sys.argv[1], strict=True)
try:
    subnet = ipaddress.ip_network(sys.argv[2], strict=False)
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if pool.overlaps(subnet) else 1)
PY
    then
      if [[ "$hosted" != "true" ]]; then
        echo "Non-Ithute Docker network $network_id ($subnet) overlaps reserved pool $NETWORK_POOL" >&2
        exit 1
      fi
      if ! python3 - "$NETWORK_POOL" "$subnet" <<'PY'
import ipaddress, sys
pool = ipaddress.ip_network(sys.argv[1], strict=True)
subnet = ipaddress.ip_network(sys.argv[2], strict=False)
raise SystemExit(0 if subnet.subnet_of(pool) else 1)
PY
      then
        echo "Hosted network $network_id is not fully contained in reserved pool $NETWORK_POOL" >&2
        exit 1
      fi
    fi
  done
done

if ! iptables -S "$CHAIN" >/dev/null 2>&1; then
  iptables -N "$CHAIN"
fi
iptables -F "$CHAIN"

# Return traffic from permitted outbound connections.
iptables -A "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Project-scoped database access reaches only the Docker host gateway and the
# explicitly configured shared DB ports.
iptables -A "$CHAIN" -d "$DB_GATEWAY_IP/32" -p tcp --dport "$POSTGRES_PORT" -j ACCEPT
iptables -A "$CHAIN" -d "$DB_GATEWAY_IP/32" -p tcp --dport "$MYSQL_PORT" -j ACCEPT

# Block cloud metadata, loopback, link-local and private east/west access before
# permitting ordinary Internet web traffic. The DB gateway exceptions above are
# intentionally evaluated first.
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

# Everything else from the reserved hosted pool is denied by default. This
# prevents direct SMTP, SSH, arbitrary database scanning and lateral movement.
iptables -A "$CHAIN" -j REJECT --reject-with icmp-port-unreachable

# Replace stale Ithute pool jumps with exactly one rule at the top of
# DOCKER-USER. Unrelated Docker forwarding rules are not flushed or rewritten.
while iptables -C DOCKER-USER -s "$NETWORK_POOL" -j "$CHAIN" 2>/dev/null; do
  iptables -D DOCKER-USER -s "$NETWORK_POOL" -j "$CHAIN"
done
iptables -I DOCKER-USER 1 -s "$NETWORK_POOL" -j "$CHAIN"

if [[ -n "$ORIGIN_BIND_IP" ]]; then
  if ! iptables -S "$INGRESS_CHAIN" >/dev/null 2>&1; then
    iptables -N "$INGRESS_CHAIN"
  fi
  iptables -F "$INGRESS_CHAIN"
  iptables -A "$INGRESS_CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  IFS=',' read -ra EDGE_CIDR_LIST <<<"$EDGE_ORIGIN_CIDRS"
  for cidr in "${EDGE_CIDR_LIST[@]}"; do
    cidr="${cidr//[[:space:]]/}"
    [[ -n "$cidr" ]] || continue
    iptables -A "$INGRESS_CHAIN" -s "$cidr" -j ACCEPT
  done
  iptables -A "$INGRESS_CHAIN" -j REJECT --reject-with icmp-port-unreachable

  # Docker DNAT occurs before DOCKER-USER. Match the original destination so
  # the rule protects only the reserved private-origin bind IP/port range.
  while iptables -C DOCKER-USER -p tcp -m conntrack --ctorigdst "$ORIGIN_BIND_IP" --ctorigdstport "$ORIGIN_PORT_START:$ORIGIN_PORT_END" -j "$INGRESS_CHAIN" 2>/dev/null; do
    iptables -D DOCKER-USER -p tcp -m conntrack --ctorigdst "$ORIGIN_BIND_IP" --ctorigdstport "$ORIGIN_PORT_START:$ORIGIN_PORT_END" -j "$INGRESS_CHAIN"
  done
  iptables -I DOCKER-USER 1 -p tcp -m conntrack --ctorigdst "$ORIGIN_BIND_IP" --ctorigdstport "$ORIGIN_PORT_START:$ORIGIN_PORT_END" -j "$INGRESS_CHAIN"
fi

echo "Ithute hosted-workload egress policy active for $NETWORK_POOL. DB gateway: $DB_GATEWAY_IP"
