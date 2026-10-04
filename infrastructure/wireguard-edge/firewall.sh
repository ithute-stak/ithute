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
