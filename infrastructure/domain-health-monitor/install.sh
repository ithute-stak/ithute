#!/usr/bin/env bash
set -euo pipefail

ITHUTE_DIR="${ITHUTE_DIR:-/opt/ithute}"
SYSTEMD_DIR=/etc/systemd/system

install -m 0644 "$ITHUTE_DIR/infrastructure/domain-health-monitor/ithute-domain-health-monitor.service" "$SYSTEMD_DIR/ithute-domain-health-monitor.service"
install -m 0644 "$ITHUTE_DIR/infrastructure/domain-health-monitor/ithute-domain-health-monitor.timer" "$SYSTEMD_DIR/ithute-domain-health-monitor.timer"
chmod +x "$ITHUTE_DIR/infrastructure/domain-health-monitor/run.sh"
systemctl daemon-reload
systemctl enable --now ithute-domain-health-monitor.timer
systemctl list-timers ithute-domain-health-monitor.timer --no-pager
