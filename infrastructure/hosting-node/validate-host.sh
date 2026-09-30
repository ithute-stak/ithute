#!/usr/bin/env bash
set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }
ok() { echo "OK: $*"; }

for binary in docker ss python3 iptables; do
  command -v "$binary" >/dev/null 2>&1 || fail "Missing required command: $binary"
done

docker info >/dev/null || fail "Docker daemon is not reachable"
ok "Docker daemon reachable"

python3 - <<'PY'
import ipaddress
import subprocess
import sys

ports = {5432: "PostgreSQL", 3306: "MySQL"}
text = subprocess.run(["ss", "-H", "-ltn"], check=True, capture_output=True, text=True).stdout
seen = set()
for line in text.splitlines():
    parts = line.split()
    if len(parts) < 4:
        continue
    local = parts[3]
    host = local.rsplit(":", 1)[0].strip("[]")
    try:
        port = int(local.rsplit(":", 1)[1])
    except ValueError:
        continue
    if port not in ports:
        continue
    seen.add(port)
    if host in {"0.0.0.0", "::", "*"}:
        raise SystemExit(f"{ports[port]} is listening on wildcard address {host}:{port}")
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        raise SystemExit(f"Could not validate {ports[port]} listener address: {host}:{port}")
    if not (ip.is_loopback or ip.is_private or ip.is_link_local):
        raise SystemExit(f"{ports[port]} is listening on public address {host}:{port}")

for port, name in ports.items():
    if port not in seen:
        print(f"INFO: {name} is not listening on TCP/{port}; engine may be intentionally disabled")
PY
ok "Database listeners are not wildcard/public"

iptables -S DOCKER-USER >/dev/null 2>&1 || fail "DOCKER-USER chain is unavailable"
if ! iptables -S ITHUTE-HOSTING-EGRESS >/dev/null 2>&1; then
  fail "ITHUTE-HOSTING-EGRESS chain is missing; run apply-egress-firewall.sh"
fi

rules="$(iptables -S ITHUTE-HOSTING-EGRESS)"
grep -Fq -- '--dport 443 -j ACCEPT' <<<"$rules" || warn "HTTPS egress is not allowed"
grep -Fq -- '-j REJECT' <<<"$rules" || fail "Hosted egress chain has no default reject"
grep -Fq -- '169.254.0.0/16' <<<"$rules" || fail "Hosted egress chain does not block link-local/cloud metadata range"
ok "Hosted egress chain has deny-by-default and metadata blocking"

mapfile -t NETWORK_IDS < <(docker network ls --filter label=ithute.hosted=true --format '{{.ID}}')
for network_id in "${NETWORK_IDS[@]}"; do
  subnet="$(docker network inspect "$network_id" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}')"
  [[ -n "$subnet" ]] || fail "Hosted network $network_id has no subnet"
  iptables -C DOCKER-USER -s "$subnet" -j ITHUTE-HOSTING-EGRESS >/dev/null 2>&1 || fail "Hosted network $network_id ($subnet) bypasses Ithute egress policy"
done
ok "All current hosted networks are attached to the scoped egress policy"

if docker ps --format '{{.Names}}' | grep -Eq '(^|[-_])(loanhub|khanya|tutor|nbros)([-_]|$)'; then
  fail "This host appears to run another product stack. Dedicated Ithute hosting nodes must not share LoanHub/Khanya/Tutor/NBros runtime hosts."
fi
ok "No known foreign product workload detected on hosting node"

echo "Hosting node boundary validation passed."
