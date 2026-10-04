#!/usr/bin/env bash
set -euo pipefail

PORT="${ITHUTE_WIREGUARD_LISTEN_PORT:-51820}"

[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || {
  echo "Invalid ITHUTE_WIREGUARD_LISTEN_PORT: $PORT" >&2
  exit 1
}

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  ufw allow "${PORT}/udp" comment 'Ithute managed private network' >/dev/null
  exit 0
fi

if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port="${PORT}/udp" >/dev/null
  firewall-cmd --reload >/dev/null
  exit 0
fi

command -v iptables >/dev/null 2>&1 || {
  echo "No supported firewall tool is available." >&2
  exit 1
}
iptables -C INPUT -p udp --dport "$PORT" -j ACCEPT >/dev/null 2>&1 ||
  iptables -I INPUT 1 -p udp --dport "$PORT" -j ACCEPT
