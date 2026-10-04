from __future__ import annotations

import shlex


def render_hosting_node_bootstrap(
    *,
    api_base_url: str,
    hosting_token: str,
    server_token: str,
    origin_bind_ip: str | None,
    edge_origin_cidrs: str,
    backup_remote: str | None,
) -> str:
    api_root = api_base_url.rstrip("/")
    origin = origin_bind_ip or ""
    backup = backup_remote or ""
    q = shlex.quote
    return f"""#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo/root." >&2
  exit 1
fi

API_ROOT={q(api_root)}
HOSTING_TOKEN={q(hosting_token)}
SERVER_TOKEN={q(server_token)}
ORIGIN_BIND_IP={q(origin)}
EDGE_ORIGIN_CIDRS={q(edge_origin_cidrs)}
BACKUP_REMOTE={q(backup)}
RAW_BASE="https://raw.githubusercontent.com/ithute-stak/ithute/main"

fail() {{ echo "ERROR: $*" >&2; exit 1; }}
info() {{ echo "INFO: $*"; }}

if ! command -v curl >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || fail "curl is required and automatic package installation is unavailable"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates
fi

if ! command -v python3 >/dev/null 2>&1 || ! command -v iptables >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || fail "python3 and iptables are required"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3 iptables
fi

if ! command -v docker >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || fail "Docker is required and automatic package installation is unavailable"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
  systemctl enable --now docker
fi

docker info >/dev/null || fail "Docker daemon is not reachable"

install -d -m 0755 /opt/ithute-hosting-agent /opt/ithute-hosting-node /opt/ithute/server-agent /var/lib/ithute-hosting/database-backups /var/log/ithute
install -d -m 0700 /etc/ithute-hosting-node /etc/ithute

fetch() {{
  local src="$1" dst="$2" mode="$3"
  curl -fsSL "$RAW_BASE/$src" -o "$dst"
  chmod "$mode" "$dst"
}}

fetch infrastructure/hosting-agent/agent.py /opt/ithute-hosting-agent/agent.py 0755
fetch infrastructure/hosting-agent/agent_v3.py /opt/ithute-hosting-agent/agent_v3.py 0755
fetch infrastructure/hosting-agent/agent_v4.py /opt/ithute-hosting-agent/agent_v4.py 0755
fetch infrastructure/hosting-agent/network_policy.py /opt/ithute-hosting-agent/network_policy.py 0644
fetch infrastructure/hosting-agent/backup_remote.py /opt/ithute-hosting-agent/backup_remote.py 0644
fetch infrastructure/hosting-node/apply-egress-firewall.sh /opt/ithute-hosting-node/apply-egress-firewall.sh 0755
fetch infrastructure/hosting-node/validate-host.sh /opt/ithute-hosting-node/validate-host.sh 0755
fetch infrastructure/hosting-node/production-acceptance.sh /opt/ithute-hosting-node/production-acceptance.sh 0755
fetch infrastructure/hosting-node/ithute-hosting-agent.service /etc/systemd/system/ithute-hosting-agent.service 0644
fetch infrastructure/hosting-node/ithute-hosting-egress.service /etc/systemd/system/ithute-hosting-egress.service 0644
fetch infrastructure/server-agent/agent.py /opt/ithute/server-agent/agent.py 0755
fetch infrastructure/server-agent/ithute-server-agent.service /etc/systemd/system/ithute-server-agent.service 0644

if ! id ithute-hosting-agent >/dev/null 2>&1; then
  useradd --system --home /var/lib/ithute-hosting --shell /usr/sbin/nologin ithute-hosting-agent
fi
usermod -aG docker ithute-hosting-agent

umask 077
cat > /etc/ithute-hosting-node/agent.env <<EOF
ITHUTE_API_URL=$API_ROOT
ITHUTE_HOSTING_AGENT_TOKEN=$HOSTING_TOKEN
ITHUTE_HOSTING_POLL_SECONDS=15
ITHUTE_HOSTING_HEARTBEAT_SECONDS=60
ITHUTE_HOSTING_IMAGE_PREFIX=ghcr.io/ithute-stak/hosted-
ITHUTE_HOSTING_NETWORK_POOL=10.240.0.0/12
ITHUTE_HOSTING_NETWORK_PREFIX=28
ITHUTE_HOSTING_DATABASE_BACKUP_ROOT=/var/lib/ithute-hosting/database-backups
ITHUTE_HOSTING_DATABASE_BACKUP_MAX_BYTES=21474836480
ITHUTE_HOSTING_BACKUP_REMOTE_REQUIRED=false
ITHUTE_HOSTING_BACKUP_REMOTE=$BACKUP_REMOTE
ITHUTE_HOSTING_RCLONE_CONFIG=/etc/ithute-hosting-node/rclone.conf
ITHUTE_HOSTING_RCLONE=rclone
ITHUTE_HOSTING_ORIGIN_BIND_IP=$ORIGIN_BIND_IP
ITHUTE_HOSTING_ORIGIN_PORT_START=22000
ITHUTE_HOSTING_ORIGIN_PORT_END=29999
ITHUTE_EDGE_ORIGIN_CIDRS=$EDGE_ORIGIN_CIDRS
ITHUTE_HOSTING_EGRESS_ALLOW_DNS=true
ITHUTE_HOSTING_EGRESS_ALLOW_HTTP=true
ITHUTE_HOSTING_EGRESS_ALLOW_HTTPS=true
EOF
chmod 0600 /etc/ithute-hosting-node/agent.env

cat > /etc/ithute/server-agent.env <<EOF
ITHUTE_API_URL=$API_ROOT/api/v1
ITHUTE_SERVER_AGENT_TOKEN=$SERVER_TOKEN
ITHUTE_SERVER_AGENT_INTERVAL=60
ITHUTE_SERVER_AGENT_TIMEOUT=10
EOF
chmod 0600 /etc/ithute/server-agent.env

if [ -n "$ORIGIN_BIND_IP" ]; then
  ip -o addr show | grep -Fq " $ORIGIN_BIND_IP/" || fail "Private origin IP $ORIGIN_BIND_IP is not assigned to this VPS yet"
fi

set -a
. /etc/ithute-hosting-node/agent.env
set +a
/opt/ithute-hosting-node/apply-egress-firewall.sh

systemctl daemon-reload
systemctl enable --now ithute-hosting-egress.service
systemctl enable --now ithute-hosting-agent.service
systemctl enable --now ithute-server-agent.service

sleep 3
/opt/ithute-hosting-node/validate-host.sh

unset HOSTING_TOKEN SERVER_TOKEN
info "Ithute hosting-node bootstrap completed."
info "The node is intentionally not activated for new projects until the control plane sees healthy agent heartbeats."
info "Open Ithute → Hosting nodes to review readiness and activate the node."
"""
