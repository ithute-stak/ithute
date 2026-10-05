#!/usr/bin/env bash
set -euo pipefail

PORT="${ITHUTE_WIREGUARD_LISTEN_PORT:-51820}"

[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || {
  echo "Invalid ITHUTE_WIREGUARD_LISTEN_PORT: $PORT" >&2
  exit 1
}

command -v iptables >/dev/null 2>&1 || {
  echo "iptables is required for the Ithute edge firewall service." >&2
  exit 1
}

iptables -C INPUT -p udp --dport "$PORT" -j ACCEPT >/dev/null 2>&1 ||
  iptables -I INPUT 1 -p udp --dport "$PORT" -j ACCEPT


MESH_CHAIN="ITHUTE_WG_MESH"

iptables -N "$MESH_CHAIN" >/dev/null 2>&1 || true
iptables -C FORWARD -i ithute0 -o ithute0 -j "$MESH_CHAIN" >/dev/null 2>&1 ||
  iptables -I FORWARD 1 -i ithute0 -o ithute0 -j "$MESH_CHAIN"

# Every enrolled Ithute node can communicate with every other enrolled node by
# default across the private WireGuard mesh. Public interfaces are unaffected.
iptables -F "$MESH_CHAIN"
iptables -A "$MESH_CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A "$MESH_CHAIN" -j ACCEPT
