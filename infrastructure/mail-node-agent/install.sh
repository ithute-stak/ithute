#!/usr/bin/env bash
set -euo pipefail

: "${ITHUTE_API_URL:?Set ITHUTE_API_URL, e.g. https://ithute.co.ls}"
: "${ITHUTE_MAIL_AGENT_TOKEN:?Set the one-time ith_mail_ agent token}"
: "${ITHUTE_MAIL_HOSTNAME:?Set the public mail-node hostname}"
: "${ITHUTE_MAIL_POSTMASTER:?Set a postmaster address}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR=/opt/ithute-mail-agent
CONFIG_DIR=/etc/ithute-mail-node
MAIL_ROOT=/srv/ithute-mail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root." >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || {
  echo "Docker Engine with the compose plugin must be installed first." >&2
  exit 2
}
docker compose version >/dev/null 2>&1 || {
  echo "Docker Compose plugin is required." >&2
  exit 2
}
command -v python3 >/dev/null 2>&1 || {
  echo "Python 3 is required." >&2
  exit 2
}
command -v rclone >/dev/null 2>&1 || {
  echo "rclone is required for mandatory off-node backups." >&2
  exit 2
}

getent group ithute-mail-agent >/dev/null || groupadd --system ithute-mail-agent
id ithute-mail-agent >/dev/null 2>&1 || useradd --system --gid ithute-mail-agent --home-dir /nonexistent --shell /usr/sbin/nologin ithute-mail-agent

install -d -m 0755 "$INSTALL_DIR" "$CONFIG_DIR"
install -d -m 0750 -o ithute-mail-agent -g ithute-mail-agent /var/lib/ithute-mail-node/backups
install -d -m 0750 "$MAIL_ROOT" "$MAIL_ROOT/config" "$MAIL_ROOT/data/mail-data" "$MAIL_ROOT/data/mail-state" "$MAIL_ROOT/data/mail-logs"
install -m 0755 "$SCRIPT_DIR/agent.py" "$INSTALL_DIR/agent.py"
install -m 0644 "$SCRIPT_DIR/compose.yml" "$MAIL_ROOT/compose.yml"
install -m 0644 "$SCRIPT_DIR/ithute-mail-agent.service" /etc/systemd/system/ithute-mail-agent.service

cat > "$MAIL_ROOT/.env" <<EOF
ITHUTE_MAIL_HOSTNAME=$ITHUTE_MAIL_HOSTNAME
ITHUTE_MAIL_POSTMASTER=$ITHUTE_MAIL_POSTMASTER
EOF
chmod 0600 "$MAIL_ROOT/.env"

cat > "$CONFIG_DIR/agent.env" <<EOF
ITHUTE_API_URL=$ITHUTE_API_URL
ITHUTE_MAIL_AGENT_TOKEN=$ITHUTE_MAIL_AGENT_TOKEN
ITHUTE_MAIL_HOSTNAME=$ITHUTE_MAIL_HOSTNAME
ITHUTE_MAIL_ACCOUNTS_FILE=$MAIL_ROOT/config/postfix-accounts.cf
ITHUTE_MAIL_QUOTAS_FILE=$MAIL_ROOT/config/dovecot-quotas.cf
ITHUTE_MAIL_STORAGE_PATH=$MAIL_ROOT/data/mail-data
ITHUTE_MAIL_BACKUP_ROOT=/var/lib/ithute-mail-node/backups
ITHUTE_MAIL_BACKUP_REMOTE_REQUIRED=true
ITHUTE_MAIL_BACKUP_REMOTE=${ITHUTE_MAIL_BACKUP_REMOTE:-}
ITHUTE_MAIL_RCLONE_CONFIG=$CONFIG_DIR/rclone.conf
ITHUTE_MAIL_CONTAINER=ithute-mail
ITHUTE_MAIL_POLL_SECONDS=10
ITHUTE_MAIL_HEARTBEAT_SECONDS=60
EOF
chmod 0600 "$CONFIG_DIR/agent.env"
chown root:ithute-mail-agent "$CONFIG_DIR/agent.env"

if [ -z "${ITHUTE_MAIL_BACKUP_REMOTE:-}" ]; then
  echo "ITHUTE_MAIL_BACKUP_REMOTE must point to off-node rclone storage before the agent can start." >&2
  exit 2
fi
test -s "$CONFIG_DIR/rclone.conf" || {
  echo "Install a mode-0600 rclone configuration at $CONFIG_DIR/rclone.conf before continuing." >&2
  exit 2
}
chmod 0600 "$CONFIG_DIR/rclone.conf"

test -d "/etc/letsencrypt/live/$ITHUTE_MAIL_HOSTNAME" || {
  echo "TLS certificate not found at /etc/letsencrypt/live/$ITHUTE_MAIL_HOSTNAME." >&2
  echo "Point DNS to this server and obtain a Let's Encrypt certificate before starting the mail node." >&2
  exit 2
}

touch "$MAIL_ROOT/config/postfix-accounts.cf" "$MAIL_ROOT/config/dovecot-quotas.cf"
chmod 0600 "$MAIL_ROOT/config/postfix-accounts.cf" "$MAIL_ROOT/config/dovecot-quotas.cf"

docker compose --env-file "$MAIL_ROOT/.env" -f "$MAIL_ROOT/compose.yml" pull
docker compose --env-file "$MAIL_ROOT/.env" -f "$MAIL_ROOT/compose.yml" up -d

systemctl daemon-reload
systemctl enable --now ithute-mail-agent.service

echo "Ithute mail node installed. Wait for SMTP/IMAP/TLS readiness to become green in Operations > Mail nodes."
