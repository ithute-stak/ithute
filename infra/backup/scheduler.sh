#!/bin/sh
set -eu

INTERVAL="${BACKUP_SCHEDULE_SECONDS:-21600}"
INITIAL_DELAY="${BACKUP_INITIAL_DELAY_SECONDS:-30}"
STATUS_DIR="/workspace/status"
mkdir -p "$STATUS_DIR"

write_health() {
  if mailbox-backup-status --json > "$STATUS_DIR/health.json.tmp"; then
    mv "$STATUS_DIR/health.json.tmp" "$STATUS_DIR/health.json"
    return 0
  fi
  if [ -s "$STATUS_DIR/health.json.tmp" ]; then
    mv "$STATUS_DIR/health.json.tmp" "$STATUS_DIR/health.json"
  else
    rm -f "$STATUS_DIR/health.json.tmp"
  fi
  return 1
}

run_backup() {
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if mailbox-backup; then
    finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    jq -n --arg status success --arg started_at "$started" --arg finished_at "$finished" \
      '{status:$status,started_at:$started_at,finished_at:$finished_at}' > "$STATUS_DIR/last-run.json.tmp"
    mv "$STATUS_DIR/last-run.json.tmp" "$STATUS_DIR/last-run.json"
    write_health || true
    return 0
  fi
  code=$?
  finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  jq -n --arg status failed --arg started_at "$started" --arg finished_at "$finished" --argjson exit_code "$code" \
    '{status:$status,started_at:$started_at,finished_at:$finished_at,exit_code:$exit_code}' > "$STATUS_DIR/last-run.json.tmp"
  mv "$STATUS_DIR/last-run.json.tmp" "$STATUS_DIR/last-run.json"
  write_health || true
  return "$code"
}

case "${1:-loop}" in
  once)
    run_backup
    ;;
  loop)
    sleep "$INITIAL_DELAY"
    while true; do
      run_backup || true
      sleep "$INTERVAL"
    done
    ;;
  *)
    echo "usage: mailbox-backup-scheduler [once|loop]" >&2
    exit 64
    ;;
esac
