#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 1
fi

for cmd in curl python3 openssl; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing required command: $cmd" >&2; exit 1; }
done

if ! command -v wg >/dev/null 2>&1 || ! command -v wg-quick >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || { echo "wireguard-tools is required" >&2; exit 1; }
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y wireguard-tools
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -d -m 0700 /etc/ithute-wireguard /etc/wireguard
install -d -m 0755 /opt/ithute-wireguard

if [ ! -s /etc/ithute-wireguard/private.key ]; then
  wg genkey > /etc/ithute-wireguard/private.key
  chmod 0600 /etc/ithute-wireguard/private.key
fi

install -m 0755 "$SCRIPT_DIR/reconcile.sh" /opt/ithute-wireguard/reconcile.sh
install -m 0644 "$SCRIPT_DIR/ithute-wireguard-edge-reconciler.service" /etc/systemd/system/ithute-wireguard-edge-reconciler.service
install -m 0644 "$SCRIPT_DIR/ithute-wireguard-edge-reconciler.timer" /etc/systemd/system/ithute-wireguard-edge-reconciler.timer

public_key="$(wg pubkey < /etc/ithute-wireguard/private.key)"
echo "Ithute Edge WireGuard public key: $public_key"
echo "Set ITHUTE_WIREGUARD_EDGE_PUBLIC_KEY to this value in Ithute's production environment."
echo "Set ITHUTE_WIREGUARD_EDGE_ENDPOINT to <edge-public-ip>:51820."
echo "Set the same strong ITHUTE_WIREGUARD_RECONCILER_TOKEN in the backend and /etc/ithute-wireguard/reconciler.env."
echo "Then enable: systemctl enable --now ithute-wireguard-edge-reconciler.timer"
