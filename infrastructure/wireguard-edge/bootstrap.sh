#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
ENV_FILE="${ITHUTE_ENV_FILE:-$APP_DIR/.env.production}"
PUBLIC_IPV4="${ITHUTE_PUBLIC_IPV4:-}"
API_URL="${ITHUTE_API_URL:-https://ithute.co.ls}"
SUBNET="${ITHUTE_WIREGUARD_SUBNET:-10.70.0.0/24}"
EDGE_ADDRESS="${ITHUTE_WIREGUARD_EDGE_ADDRESS:-10.70.0.1}"
LISTEN_PORT="${ITHUTE_WIREGUARD_LISTEN_PORT:-51820}"
WG_DIR="/etc/ithute-wireguard"
WG_PRIVATE_KEY="$WG_DIR/private.key"
RECONCILER_ENV="$WG_DIR/reconciler.env"

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }

[[ -n "$PUBLIC_IPV4" ]] || fail "ITHUTE_PUBLIC_IPV4 is required"
[[ -f "$ENV_FILE" ]] || fail "Production environment file does not exist: $ENV_FILE"

for cmd in curl python3 openssl; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing required command: $cmd"
done

if ! command -v wg >/dev/null 2>&1 || ! command -v wg-quick >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || fail "wireguard-tools is required"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y wireguard-tools
fi

python3 - "$PUBLIC_IPV4" "$SUBNET" "$EDGE_ADDRESS" "$LISTEN_PORT" <<'PY'
import ipaddress, sys
public_ip = ipaddress.ip_address(sys.argv[1])
subnet = ipaddress.ip_network(sys.argv[2], strict=False)
edge = ipaddress.ip_address(sys.argv[3])
port = int(sys.argv[4])
if not isinstance(public_ip, ipaddress.IPv4Address):
    raise SystemExit("ITHUTE_PUBLIC_IPV4 must be IPv4")
if not isinstance(subnet, ipaddress.IPv4Network) or not subnet.is_private or not 20 <= subnet.prefixlen <= 29:
    raise SystemExit("ITHUTE_WIREGUARD_SUBNET must be a private IPv4 /20 to /29")
if edge not in subnet or edge in {subnet.network_address, subnet.broadcast_address}:
    raise SystemExit("ITHUTE_WIREGUARD_EDGE_ADDRESS must be a usable address inside the subnet")
if not 1 <= port <= 65535:
    raise SystemExit("ITHUTE_WIREGUARD_LISTEN_PORT must be a valid UDP port")
PY

install -d -m 0700 "$WG_DIR" /etc/wireguard
install -d -m 0755 /opt/ithute-wireguard

if [ ! -s "$WG_PRIVATE_KEY" ]; then
  wg genkey > "$WG_PRIVATE_KEY"
  chmod 0600 "$WG_PRIVATE_KEY"
fi
EDGE_PUBLIC_KEY="$(wg pubkey < "$WG_PRIVATE_KEY")"

read_env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n1
}

RECONCILER_TOKEN="$(read_env_value ITHUTE_WIREGUARD_RECONCILER_TOKEN)"
if [ -z "$RECONCILER_TOKEN" ]; then
  RECONCILER_TOKEN="$(openssl rand -hex 32)"
fi

python3 - "$ENV_FILE" "$SUBNET" "$EDGE_ADDRESS" "$EDGE_PUBLIC_KEY" "$PUBLIC_IPV4:$LISTEN_PORT" "$LISTEN_PORT" "$RECONCILER_TOKEN" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
pairs = {
    "ITHUTE_HOSTING_ORIGIN_CIDRS": sys.argv[2],
    "ITHUTE_WIREGUARD_SUBNET": sys.argv[2],
    "ITHUTE_WIREGUARD_EDGE_ADDRESS": sys.argv[3],
    "ITHUTE_WIREGUARD_EDGE_PUBLIC_KEY": sys.argv[4],
    "ITHUTE_WIREGUARD_EDGE_ENDPOINT": sys.argv[5],
    "ITHUTE_WIREGUARD_LISTEN_PORT": sys.argv[6],
    "ITHUTE_WIREGUARD_RECONCILER_TOKEN": sys.argv[7],
}
lines = path.read_text(encoding="utf-8").splitlines()
out = []
seen = set()
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in pairs:
            if key not in seen:
                out.append(f"{key}={pairs[key]}")
                seen.add(key)
            continue
    out.append(line)
if out and out[-1].strip():
    out.append("")
out.append("# Ithute-managed private hosting network")
for key, value in pairs.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
chmod 0600 "$ENV_FILE"

cat > "$RECONCILER_ENV" <<EOF
ITHUTE_API_URL=$API_URL
ITHUTE_WIREGUARD_RECONCILER_TOKEN=$RECONCILER_TOKEN
EOF
chmod 0600 "$RECONCILER_ENV"

cat > /etc/wireguard/ithute0.conf <<EOF
[Interface]
PrivateKey = $(cat "$WG_PRIVATE_KEY")
Address = $EDGE_ADDRESS/$(python3 - "$SUBNET" <<'PY'
import ipaddress, sys
print(ipaddress.ip_network(sys.argv[1], strict=False).prefixlen)
PY
)
ListenPort = $LISTEN_PORT
EOF
chmod 0600 /etc/wireguard/ithute0.conf

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -m 0755 "$SCRIPT_DIR/reconcile.sh" /opt/ithute-wireguard/reconcile.sh
install -m 0644 "$SCRIPT_DIR/ithute-wireguard-edge-reconciler.service" /etc/systemd/system/ithute-wireguard-edge-reconciler.service
install -m 0644 "$SCRIPT_DIR/ithute-wireguard-edge-reconciler.timer" /etc/systemd/system/ithute-wireguard-edge-reconciler.timer

open_udp_port() {
  local port="$1"
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    ufw allow "${port}/udp" comment 'Ithute managed private network' >/dev/null
    return
  fi
  if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port="${port}/udp" >/dev/null
    firewall-cmd --reload >/dev/null
    return
  fi
  if command -v iptables >/dev/null 2>&1; then
    iptables -C INPUT -p udp --dport "$port" -j ACCEPT >/dev/null 2>&1 || iptables -I INPUT 1 -p udp --dport "$port" -j ACCEPT
    info "Opened UDP $port with iptables. Ensure your provider firewall/security group also permits this port."
    return
  fi
  fail "No supported host firewall tool found to permit UDP $port"
}
open_udp_port "$LISTEN_PORT"

systemctl daemon-reload
systemctl enable --now wg-quick@ithute0 >/dev/null
systemctl enable --now ithute-wireguard-edge-reconciler.timer >/dev/null

ip -4 -o addr show dev ithute0 | grep -Fq " $EDGE_ADDRESS/" || fail "ithute0 did not receive the configured edge address"
test "$(wg show ithute0 listen-port)" = "$LISTEN_PORT" || fail "ithute0 is not listening on the configured UDP port"

info "Ithute Edge managed private network configured."
info "Edge address: $EDGE_ADDRESS"
info "Edge endpoint: $PUBLIC_IPV4:$LISTEN_PORT"
info "The reconciler timer is enabled and will become active after the Ithute API is deployed."
