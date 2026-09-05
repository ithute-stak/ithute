#!/bin/sh
set -eu

MAX_AGE_SECONDS="${BACKUP_MAX_AGE_SECONDS:-93600}"
MODE="${1:---json}"

if ! command -v restic >/dev/null 2>&1; then
  echo '{"healthy":false,"error":"restic unavailable"}'
  exit 2
fi

if ! snapshots="$(restic snapshots --tag mailbox-dns --json 2>/dev/null)"; then
  echo '{"healthy":false,"error":"backup repository unavailable"}'
  exit 2
fi

count="$(printf '%s' "$snapshots" | jq 'length')"
if [ "$count" -eq 0 ]; then
  echo '{"healthy":false,"snapshot_count":0,"error":"no backup snapshots"}'
  exit 1
fi

latest_time="$(printf '%s' "$snapshots" | jq -r 'sort_by(.time) | last | .time')"
latest_id="$(printf '%s' "$snapshots" | jq -r 'sort_by(.time) | last | .short_id // .id')"
latest_epoch="$(date -d "$latest_time" +%s)"
now_epoch="$(date +%s)"
age="$((now_epoch - latest_epoch))"
if [ "$age" -lt 0 ]; then age=0; fi
healthy=true
if [ "$age" -gt "$MAX_AGE_SECONDS" ]; then healthy=false; fi

result="$(jq -n \
  --argjson healthy "$healthy" \
  --arg latest_snapshot "$latest_id" \
  --arg latest_time "$latest_time" \
  --argjson age_seconds "$age" \
  --argjson max_age_seconds "$MAX_AGE_SECONDS" \
  --argjson snapshot_count "$count" \
  '{healthy:$healthy,latest_snapshot:$latest_snapshot,latest_time:$latest_time,age_seconds:$age_seconds,max_age_seconds:$max_age_seconds,snapshot_count:$snapshot_count}')"

printf '%s\n' "$result"
if [ "$MODE" = "--health" ] && [ "$healthy" != "true" ]; then
  exit 1
fi
