#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Run as root"; exit 1; fi
install -d -m 0755 /opt/ithute/server-agent /etc/ithute /var/log/ithute
install -d -m 0700 /var/lib/ithute/server-agent
install -m 0755 agent.py /opt/ithute/server-agent/agent.py
install -m 0644 ithute-server-agent.service /etc/systemd/system/ithute-server-agent.service
if [ ! -f /etc/ithute/server-agent.env ]; then
  install -m 0600 agent.env.example /etc/ithute/server-agent.env
fi
systemctl daemon-reload
systemctl enable ithute-server-agent.service
echo "Edit /etc/ithute/server-agent.env with the one-time token, then run: systemctl restart ithute-server-agent"
