#!/bin/sh
set -eu

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
STATUS_DIR="${BACKUP_STATUS_DIR:-/backup-status/status}"
DRILL_HOST="${RESTORE_DRILL_DB_HOST:-ithute-restore-drill-db}"
DRILL_USER="${RESTORE_DRILL_DB_USER:-ithute_restore}"
DRILL_PASSWORD="${RESTORE_DRILL_DB_PASSWORD}"
INTERVAL_SECONDS="${RESTORE_DRILL_INTERVAL_SECONDS:-604800}"
INITIAL_DELAY_SECONDS="${RESTORE_DRILL_INITIAL_DELAY_SECONDS:-120}"

mkdir -p "$STATUS_DIR"

iso_now() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

latest_dump() {
  label="$1"
  find "$BACKUP_ROOT" -maxdepth 1 -type f -name "${label}-*.dump" -print | sort | tail -n 1
}

wait_for_db() {
  attempt=0
  while [ "$attempt" -lt 60 ]; do
    if PGPASSWORD="$DRILL_PASSWORD" pg_isready -h "$DRILL_HOST" -U "$DRILL_USER" -d postgres >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done
  return 1
}

record_result() {
  status="$1"
  detail="$2"
  started_at="$3"
  finished_at="$4"
  run_id="$5"
  safe_detail=$(printf '%s' "$detail" | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '{"run_id":"%s","status":"%s","started_at":"%s","finished_at":"%s","databases":["app","auth","push","realtime"],"detail":"%s"}\n' \
    "$run_id" "$status" "$started_at" "$finished_at" "$safe_detail" >> "$STATUS_DIR/restore-drills.jsonl"
  tail -n 200 "$STATUS_DIR/restore-drills.jsonl" > "$STATUS_DIR/restore-drills.jsonl.tmp"
  mv "$STATUS_DIR/restore-drills.jsonl.tmp" "$STATUS_DIR/restore-drills.jsonl"
}

run_drill() {
  run_id="restore-$(date -u '+%Y%m%dT%H%M%SZ')"
  started_at="$(iso_now)"
  if ! wait_for_db; then
    record_result failed "Restore-drill PostgreSQL did not become ready." "$started_at" "$(iso_now)" "$run_id"
    return 1
  fi

  for label in app auth push realtime; do
    dump="$(latest_dump "$label")"
    if [ -z "$dump" ] || [ ! -s "$dump" ]; then
      record_result failed "No usable ${label} backup exists." "$started_at" "$(iso_now)" "$run_id"
      return 1
    fi
    checksum_file="${dump}.sha256"
    if [ ! -s "$checksum_file" ]; then
      record_result failed "Missing checksum for ${label} backup." "$started_at" "$(iso_now)" "$run_id"
      return 1
    fi
    if ! (cd "$BACKUP_ROOT" && sha256sum -c "$(basename "$checksum_file")" >/dev/null 2>&1); then
      record_result failed "Checksum verification failed for ${label} backup." "$started_at" "$(iso_now)" "$run_id"
      return 1
    fi
    db="drill_${label}"
    PGPASSWORD="$DRILL_PASSWORD" dropdb --if-exists -h "$DRILL_HOST" -U "$DRILL_USER" "$db" >/dev/null 2>&1 || true
    if ! PGPASSWORD="$DRILL_PASSWORD" createdb -h "$DRILL_HOST" -U "$DRILL_USER" "$db"; then
      record_result failed "Unable to create isolated restore database for ${label}." "$started_at" "$(iso_now)" "$run_id"
      return 1
    fi
    if ! PGPASSWORD="$DRILL_PASSWORD" pg_restore --exit-on-error --no-owner --no-privileges -h "$DRILL_HOST" -U "$DRILL_USER" -d "$db" "$dump" >/tmp/restore-${label}.log 2>&1; then
      detail="Restore failed for ${label}: $(tail -n 3 /tmp/restore-${label}.log | tr '\n' ' ' | cut -c1-500)"
      record_result failed "$detail" "$started_at" "$(iso_now)" "$run_id"
      return 1
    fi
    if ! PGPASSWORD="$DRILL_PASSWORD" psql -h "$DRILL_HOST" -U "$DRILL_USER" -d "$db" -v ON_ERROR_STOP=1 -Atqc 'SELECT 1' | grep -Fxq 1; then
      record_result failed "Integrity query failed after restoring ${label}." "$started_at" "$(iso_now)" "$run_id"
      return 1
    fi
  done

  record_result success "All four control-plane PostgreSQL backups restored successfully into isolated drill databases and passed connectivity checks." "$started_at" "$(iso_now)" "$run_id"
  return 0
}

sleep "$INITIAL_DELAY_SECONDS"
while true; do
  run_drill || true
  sleep "$INTERVAL_SECONDS"
done
