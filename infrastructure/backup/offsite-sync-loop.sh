#!/bin/sh
set -eu

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
STATUS_DIR="${BACKUP_STATUS_DIR:-/backup-status/status}"
REMOTE="${BACKUP_REMOTE:?BACKUP_REMOTE is required, e.g. immutable:ithute/control-plane}"
CONFIG="${RCLONE_CONFIG:-/config/rclone.conf}"
INTERVAL_SECONDS="${OFFSITE_SYNC_INTERVAL_SECONDS:-3600}"

mkdir -p "$STATUS_DIR"

iso_now() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

json_string() {
  value=${1:-}
  value=$(printf '%s' "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '"%s"' "$value"
}

record() {
  healthy="$1"
  detail="$2"
  checked_at="$(iso_now)"
  tmp="$STATUS_DIR/offsite.json.tmp"
  {
    printf '{\n'
    printf '  "healthy": %s,\n' "$healthy"
    printf '  "mode": "append_only",\n'
    printf '  "checked_at": %s,\n' "$(json_string "$checked_at")"
    printf '  "remote": %s,\n' "$(json_string "$REMOTE")"
    printf '  "detail": %s\n' "$(json_string "$detail")"
    printf '}\n'
  } > "$tmp"
  mv "$tmp" "$STATUS_DIR/offsite.json"
}

sync_cycle() {
  if [ ! -s "$CONFIG" ]; then
    record false "Independent off-site rclone configuration is missing."
    return 1
  fi

  # --immutable refuses to modify an existing object. No delete operation is
  # ever issued by this worker; retention belongs to remote object-lock policy.
  if ! rclone copy "$BACKUP_ROOT" "$REMOTE"       --config "$CONFIG"       --immutable       --include '*.dump'       --include '*.dump.sha256'       --exclude '*'       --checkers 4       --transfers 2; then
    record false "Append-only off-site copy failed."
    return 1
  fi

  if ! rclone check "$BACKUP_ROOT" "$REMOTE"       --config "$CONFIG"       --one-way       --include '*.dump'       --include '*.dump.sha256'       --exclude '*'       --checkers 4; then
    record false "Off-site verification failed after copy."
    return 1
  fi

  record true "Control-plane backups are copied and verified in the append-only off-site repository."
}

while true; do
  sync_cycle || true
  sleep "$INTERVAL_SECONDS"
done
