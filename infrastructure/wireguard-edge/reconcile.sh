#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ITHUTE_WIREGUARD_ENV_FILE:-/etc/ithute-wireguard/reconciler.env}"
PRIVATE_KEY_FILE="${ITHUTE_WIREGUARD_PRIVATE_KEY_FILE:-/etc/ithute-wireguard/private.key}"
CONFIG_FILE="${ITHUTE_WIREGUARD_CONFIG_FILE:-/etc/wireguard/ithute0.conf}"

[[ -r "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

: "${ITHUTE_API_URL:?ITHUTE_API_URL is required}"
: "${ITHUTE_WIREGUARD_RECONCILER_TOKEN:?ITHUTE_WIREGUARD_RECONCILER_TOKEN is required}"
[[ -r "$PRIVATE_KEY_FILE" ]] || { echo "Missing WireGuard private key: $PRIVATE_KEY_FILE" >&2; exit 1; }

umask 077
tmp_json="$(mktemp)"
tmp_conf="$(mktemp)"
tmp_grants="$(mktemp)"
trap 'rm -f "$tmp_json" "$tmp_conf" "$tmp_grants"' EXIT

curl --connect-timeout 5 \
  --max-time 15 \
  --retry 1 \
  --retry-delay 2 \
  --retry-all-errors \
  -fsS \
  -H "X-Ithute-WireGuard-Reconciler: $ITHUTE_WIREGUARD_RECONCILER_TOKEN" \
  "${ITHUTE_API_URL%/}/api/v1/infrastructure/private-network/edge-peers" > "$tmp_json"

PRIVATE_KEY="$(cat "$PRIVATE_KEY_FILE")" PEERS_JSON="$(cat "$tmp_json")" python3 - "$tmp_conf" <<'PY'
import json, os, pathlib, sys
data = json.loads(os.environ["PEERS_JSON"])
private_key = os.environ["PRIVATE_KEY"].strip()
edge_address = str(data["edge_address"])
listen_port = int(data["listen_port"])
if not private_key:
    raise SystemExit("edge private key is empty")
lines = [
    "[Interface]",
    f"PrivateKey = {private_key}",
    f"Address = {edge_address}",
    f"ListenPort = {listen_port}",
    "",
]
for peer in data.get("peers", []):
    lines.extend([
        "[Peer]",
        f"PublicKey = {peer['public_key']}",
        f"AllowedIPs = {peer['allowed_ip']}",
        "",
    ])
pathlib.Path(sys.argv[1]).write_text("\n".join(lines), encoding="utf-8")
PY

python3 - "$tmp_json" "$tmp_grants" <<'PY'
import ipaddress
import json
import pathlib
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
network = ipaddress.ip_network(str(data["subnet"]), strict=False)
rows = []
for grant in data.get("grants", []):
    if not isinstance(grant, dict):
        continue
    source = ipaddress.ip_address(str(grant.get("source_ip") or ""))
    target = ipaddress.ip_address(str(grant.get("target_ip") or ""))
    protocol = str(grant.get("protocol") or "").lower()
    port = int(grant.get("port") or 0)
    if source not in network or target not in network or source == target:
        raise SystemExit("edge policy contains an invalid peer address")
    if protocol not in {"tcp", "udp"} or not 1 <= port <= 65535:
        raise SystemExit("edge policy contains an invalid protocol or port")
    rows.append(f"{source}\t{target}\t{protocol}\t{port}")
pathlib.Path(sys.argv[2]).write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
PY

install -d -m 0700 "$(dirname "$CONFIG_FILE")"
install -m 0600 "$tmp_conf" "$CONFIG_FILE"

if ! ip link show ithute0 >/dev/null 2>&1; then
  wg-quick up ithute0
else
  edge_cidr="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["edge_address"])' "$tmp_json")"
  ip address replace "$edge_cidr" dev ithute0
  wg syncconf ithute0 <(wg-quick strip "$CONFIG_FILE")
fi

MESH_CHAIN="ITHUTE_WG_MESH"
iptables -N "$MESH_CHAIN" >/dev/null 2>&1 || true
iptables -C FORWARD -i ithute0 -o ithute0 -j "$MESH_CHAIN" >/dev/null 2>&1 ||
  iptables -I FORWARD 1 -i ithute0 -o ithute0 -j "$MESH_CHAIN"
iptables -F "$MESH_CHAIN"
iptables -A "$MESH_CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A "$MESH_CHAIN" -j ACCEPT
