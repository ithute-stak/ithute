#!/bin/sh
set -eu

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY is required}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD is required}"
: "${RESTORE_DB_HOST:=restore-postgres}"
: "${RESTORE_DB_PORT:=5432}"
: "${RESTORE_DB_USER:=restore}"
: "${RESTORE_DB_PASSWORD:=restore_dev_password}"

STATUS_DIR="/workspace/status"
mkdir -p "$STATUS_DIR"
DRILL_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TARGET="/restore/latest"
rm -rf "$TARGET"
mkdir -p "$TARGET"

echo "Restoring latest encrypted snapshot into isolated drill workspace..."
restic restore latest --tag mailbox-dns --target "$TARGET"

APP_DUMP="$(find "$TARGET" -path '*/db/application.dump' -type f | head -n 1)"
PDNS_DUMP="$(find "$TARGET" -path '*/db/powerdns.dump' -type f | head -n 1)"
AUTH_DUMP="$(find "$TARGET" -path '*/db/ithute-auth.dump' -type f | head -n 1)"
MANIFEST="$(find "$TARGET" -name manifest.json -type f | head -n 1)"

[ -n "$APP_DUMP" ] && [ -f "$APP_DUMP" ] || { echo "application dump missing from restore" >&2; exit 3; }
[ -n "$PDNS_DUMP" ] && [ -f "$PDNS_DUMP" ] || { echo "PowerDNS dump missing from restore" >&2; exit 3; }
[ -n "$MANIFEST" ] && [ -f "$MANIFEST" ] || { echo "backup manifest missing from restore" >&2; exit 3; }

pg_restore --list "$APP_DUMP" >/dev/null
pg_restore --list "$PDNS_DUMP" >/dev/null
jq -e '(.schema_version == 1 or .schema_version == 2) and .application_database.sha256 and .powerdns_database.sha256' "$MANIFEST" >/dev/null

APP_EXPECTED="$(jq -r '.application_database.sha256' "$MANIFEST")"
PDNS_EXPECTED="$(jq -r '.powerdns_database.sha256' "$MANIFEST")"
[ "$(sha256sum "$APP_DUMP" | awk '{print $1}')" = "$APP_EXPECTED" ] || { echo "application dump checksum mismatch" >&2; exit 4; }
[ "$(sha256sum "$PDNS_DUMP" | awk '{print $1}')" = "$PDNS_EXPECTED" ] || { echo "PowerDNS dump checksum mismatch" >&2; exit 4; }

AUTH_EXPECTED="$(jq -r '.identity_database.sha256 // empty' "$MANIFEST")"
if [ -n "$AUTH_EXPECTED" ]; then
  [ -n "$AUTH_DUMP" ] && [ -f "$AUTH_DUMP" ] || { echo "!thute Auth dump missing from restore" >&2; exit 3; }
  pg_restore --list "$AUTH_DUMP" >/dev/null
  [ "$(sha256sum "$AUTH_DUMP" | awk '{print $1}')" = "$AUTH_EXPECTED" ] || { echo "!thute Auth dump checksum mismatch" >&2; exit 4; }
fi

export PGPASSWORD="$RESTORE_DB_PASSWORD"
for i in $(seq 1 30); do
  if pg_isready -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
pg_isready -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" >/dev/null

psql -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" -d postgres -v ON_ERROR_STOP=1 <<'SQL'
DROP DATABASE IF EXISTS mailbox_restore_app;
DROP DATABASE IF EXISTS mailbox_restore_pdns;
DROP DATABASE IF EXISTS mailbox_restore_auth;
CREATE DATABASE mailbox_restore_app;
CREATE DATABASE mailbox_restore_pdns;
CREATE DATABASE mailbox_restore_auth;
SQL

pg_restore --no-owner --no-privileges -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" -d mailbox_restore_app "$APP_DUMP"
pg_restore --no-owner --no-privileges -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" -d mailbox_restore_pdns "$PDNS_DUMP"
if [ -n "$AUTH_EXPECTED" ]; then
  pg_restore --no-owner --no-privileges -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" -d mailbox_restore_auth "$AUTH_DUMP"
fi

APP_TABLES="$(psql -At -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" -d mailbox_restore_app -c "select count(*) from pg_tables where schemaname='public'")"
PDNS_TABLES="$(psql -At -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" -d mailbox_restore_pdns -c "select count(*) from pg_tables where schemaname='public'")"
AUTH_TABLES=0
if [ -n "$AUTH_EXPECTED" ]; then
  AUTH_TABLES="$(psql -At -h "$RESTORE_DB_HOST" -p "$RESTORE_DB_PORT" -U "$RESTORE_DB_USER" -d mailbox_restore_auth -c "select count(*) from pg_tables where schemaname='public'")"
fi

[ "$APP_TABLES" -gt 0 ] || { echo "application restore contains no tables" >&2; exit 5; }
[ "$PDNS_TABLES" -gt 0 ] || { echo "PowerDNS restore contains no tables" >&2; exit 5; }
if [ -n "$AUTH_EXPECTED" ]; then
  [ "$AUTH_TABLES" -gt 0 ] || { echo "!thute Auth restore contains no tables" >&2; exit 5; }
fi

MAIL_FILES="$(find "$TARGET/data/mail" -type f 2>/dev/null | wc -l | tr -d ' ')"
EXPECTED_MAIL_FILES="$(jq -r '.maildir_file_count' "$MANIFEST")"
[ "$MAIL_FILES" -eq "$EXPECTED_MAIL_FILES" ] || { echo "Maildir restored file count mismatch" >&2; exit 5; }

DRILL_FINISHED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SNAPSHOT_ID="$(restic snapshots --tag mailbox-dns --json | jq -r 'sort_by(.time) | last | .short_id // .id')"
jq -nc \
  --arg status success \
  --arg started_at "$DRILL_STARTED" \
  --arg finished_at "$DRILL_FINISHED" \
  --arg snapshot "$SNAPSHOT_ID" \
  --argjson application_tables "$APP_TABLES" \
  --argjson powerdns_tables "$PDNS_TABLES" \
  --argjson auth_tables "$AUTH_TABLES" \
  --argjson maildir_files "$MAIL_FILES" \
  '{status:$status,started_at:$started_at,finished_at:$finished_at,snapshot:$snapshot,application_tables:$application_tables,powerdns_tables:$powerdns_tables,auth_tables:$auth_tables,maildir_files:$maildir_files}' \
  >> "$STATUS_DIR/restore-drills.jsonl"

echo "Restore drill passed: app_tables=$APP_TABLES pdns_tables=$PDNS_TABLES auth_tables=$AUTH_TABLES mail_files=$MAIL_FILES"
