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

NETWORK_POOL="${ITHUTE_HOSTING_NETWORK_POOL:-10.240.0.0/12}"
NETWORK_PREFIX="${ITHUTE_HOSTING_NETWORK_PREFIX:-28}"

python3 - "$NETWORK_POOL" "$NETWORK_PREFIX" <<'PY'
import ipaddress, sys
pool = ipaddress.ip_network(sys.argv[1], strict=True)
prefix = int(sys.argv[2])
if not isinstance(pool, ipaddress.IPv4Network) or not pool.is_private:
    raise SystemExit("Reserved hosted network pool must be private IPv4")
if prefix < pool.prefixlen or prefix > 28:
    raise SystemExit("Hosted project prefix must be between the pool prefix and /28")
PY
ok "Reserved hosted network pool is valid: $NETWORK_POOL /$NETWORK_PREFIX"

python3 - <<'PY'
import ipaddress
import subprocess

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
iptables -S ITHUTE-HOSTING-EGRESS >/dev/null 2>&1 || fail "ITHUTE-HOSTING-EGRESS chain is missing; run apply-egress-firewall.sh"
iptablestest="$(iptables -S ITHUTE-HOSTING-EGRESS)"
grep -Fq -- '--dport 443 -j ACCEPT' <<<"$iptablestest" || warn "HTTPS egress is not allowed"
grep -Fq -- '-j REJECT' <<<"$iptablestest" || fail "Hosted egress chain has no default reject"
grep -Fq -- '169.254.0.0/16' <<<"$iptablestest" || fail "Hosted egress chain does not block link-local/cloud metadata range"
iptables -C DOCKER-USER -s "$NETWORK_POOL" -j ITHUTE-HOSTING-EGRESS >/dev/null 2>&1 || fail "Reserved hosted pool bypasses Ithute egress chain"
ok "Reserved hosted pool is attached to deny-by-default egress policy"

mapfile -t NETWORK_IDS < <(docker network ls --format '{{.ID}}')
for network_id in "${NETWORK_IDS[@]}"; do
  hosted="$(docker network inspect "$network_id" --format '{{index .Labels "ithute.hosted"}}' 2>/dev/null || true)"
  mapfile -t subnets < <(docker network inspect "$network_id" --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' 2>/dev/null || true)
  for subnet in "${subnets[@]}"; do
    [[ -n "$subnet" ]] || continue
    relation="$(python3 - "$NETWORK_POOL" "$subnet" <<'PY'
import ipaddress, sys
pool = ipaddress.ip_network(sys.argv[1], strict=True)
try:
    subnet = ipaddress.ip_network(sys.argv[2], strict=False)
except ValueError:
    print("invalid")
    raise SystemExit
if not pool.overlaps(subnet):
    print("outside")
elif subnet.subnet_of(pool):
    print("inside")
else:
    print("partial")
PY
)"
    case "$relation" in
      outside) ;;
      inside)
        [[ "$hosted" == "true" ]] || fail "Non-Ithute Docker network $network_id ($subnet) occupies reserved hosted pool"
        ;;
      partial) fail "Docker network $network_id ($subnet) partially overlaps reserved hosted pool" ;;
      *) fail "Unable to validate subnet $subnet for Docker network $network_id" ;;
    esac
  done
done
ok "Reserved pool is occupied only by labeled Ithute hosted networks"

if docker ps --format '{{.Names}}' | grep -Eq '(^|[-_])(loanhub|khanya|tutor|nbros)([-_]|$)'; then
  fail "This host appears to run another product stack. Dedicated Ithute hosting nodes must not share LoanHub/Khanya/Tutor/NBros runtime hosts."
fi
ok "No known foreign product workload detected on hosting node"

echo "Hosting node boundary validation passed."
