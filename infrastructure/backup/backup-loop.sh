#!/bin/sh
set -eu

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
STATUS_DIR="${BACKUP_STATUS_DIR:-/backup-status/status}"
INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-21600}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_ROOT" "$STATUS_DIR"

iso_now() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

json_string() {
  value=${1:-}
  value=$(printf '%s' "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '"%s"' "$value"
}

write_health() {
  healthy="$1"
  detail="$2"
  checked_at="$(iso_now)"
  tmp="$STATUS_DIR/health.json.tmp"
  {
    printf '{\n'
    printf '  "healthy": %s,\n' "$healthy"
    printf '  "repository_type": "local_docker_volume",\n'
    printf '  "checked_at": %s,\n' "$(json_string "$checked_at")"
    printf '  "detail": %s\n' "$(json_string "$detail")"
    printf '}\n'
  } > "$tmp"
  mv "$tmp" "$STATUS_DIR/health.json"
}

backup_one() {
  label="$1"
  host="$2"
  database="$3"
  user="$4"
  password="$5"
  run_id="$6"
  output="$BACKUP_ROOT/${label}-${run_id}.dump"
  partial="${output}.partial"
  rm -f "$partial"
  if PGPASSWORD="$password" pg_dump \
      --host "$host" \
      --username "$user" \
      --dbname "$database" \
      --format custom \
      --compress 6 \
      --no-owner \
      --no-privileges \
      --file "$partial"; then
    mv "$partial" "$output"
    bytes="$(wc -c < "$output" | tr -d ' ')"
    printf '%s|%s|%s\n' "$label" "$output" "$bytes"
    return 0
  fi
  rm -f "$partial"
  return 1
}

run_cycle() {
  run_id="$(date -u '+%Y%m%dT%H%M%SZ')"
  started_at="$(iso_now)"
  manifest="$STATUS_DIR/.manifest-${run_id}"
  : > "$manifest"
  failed=""

  backup_one app ithute-app-db "${ITHUTE_APP_DB_NAME:-ithute_app}" "${ITHUTE_APP_DB_USER:-ithute_app}" "${ITHUTE_APP_DB_PASSWORD}" "$run_id" >> "$manifest" || failed="app"
  backup_one auth ithute-auth-db "${ITHUTE_AUTH_DB_NAME:-ithute_auth}" "${ITHUTE_AUTH_DB_USER:-ithute_auth}" "${ITHUTE_AUTH_DB_PASSWORD}" "$run_id" >> "$manifest" || failed="${failed:+$failed,}auth"
  backup_one push ithute-push-db "${ITHUTE_PUSH_DB_NAME:-ithute_push}" "${ITHUTE_PUSH_DB_USER:-ithute_push}" "${ITHUTE_PUSH_DB_PASSWORD}" "$run_id" >> "$manifest" || failed="${failed:+$failed,}push"
  backup_one realtime ithute-realtime-db "${ITHUTE_REALTIME_DB_NAME:-ithute_realtime}" "${ITHUTE_REALTIME_DB_USER:-ithute_realtime}" "${ITHUTE_REALTIME_DB_PASSWORD}" "$run_id" >> "$manifest" || failed="${failed:+$failed,}realtime"

  finished_at="$(iso_now)"
  tmp="$STATUS_DIR/last-run.json.tmp"
  status="success"
  if [ -n "$failed" ]; then status="failed"; fi

  {
    printf '{\n'
    printf '  "status": %s,\n' "$(json_string "$status")"
    printf '  "run_id": %s,\n' "$(json_string "$run_id")"
    printf '  "started_at": %s,\n' "$(json_string "$started_at")"
    printf '  "finished_at": %s,\n' "$(json_string "$finished_at")"
    printf '  "failed_databases": %s,\n' "$(json_string "$failed")"
    printf '  "databases": ['
    first=1
    while IFS='|' read -r label file bytes; do
      [ -n "$label" ] || continue
      if [ "$first" -eq 0 ]; then printf ','; fi
      first=0
      printf '\n    {"name": %s, "file": %s, "bytes": %s}' "$(json_string "$label")" "$(json_string "$file")" "$bytes"
    done < "$manifest"
    if [ "$first" -eq 0 ]; then printf '\n  '; fi
    printf ']\n'
    printf '}\n'
  } > "$tmp"
  mv "$tmp" "$STATUS_DIR/last-run.json"
  rm -f "$manifest"

  find "$BACKUP_ROOT" -type f -name '*.dump' -mtime "+$RETENTION_DAYS" -delete || true

  if [ "$status" = "success" ]; then
    write_health true "All Ithute PostgreSQL control-plane databases were backed up successfully."
    return 0
  fi
  write_health false "Backup failed for: $failed"
  return 1
}

while true; do
  run_cycle || true
  sleep "$INTERVAL_SECONDS"
done
