#!/bin/sh
set -eu

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY is required}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD is required}"
: "${APP_DB_HOST:=postgres}"
: "${APP_DB_PORT:=5432}"
: "${APP_DB_NAME:=lelefamail}"
: "${APP_DB_USER:=lelefamail}"
: "${APP_DB_PASSWORD:=lelefamail_dev_password}"
: "${PDNS_DB_HOST:=powerdns-db}"
: "${PDNS_DB_PORT:=5432}"
: "${PDNS_DB_NAME:=powerdns}"
: "${PDNS_DB_USER:=powerdns}"
: "${PDNS_DB_PASSWORD:=powerdns_dev_password}"
: "${AUTH_DB_HOST:=ithute-auth-db}"
: "${AUTH_DB_PORT:=5432}"
: "${AUTH_DB_NAME:=ithute_auth}"
: "${AUTH_DB_USER:=ithute_auth}"
: "${AUTH_DB_PASSWORD:=}"
: "${BACKUP_KEEP_DAILY:=7}"
: "${BACKUP_KEEP_WEEKLY:=5}"
: "${BACKUP_KEEP_MONTHLY:=12}"

case "$RESTIC_REPOSITORY" in
  /repository|local:/repository) ;;
  *) : ;;
esac

if [ "${#RESTIC_PASSWORD}" -lt 16 ]; then
  echo "RESTIC_PASSWORD must be at least 16 characters" >&2
  exit 2
fi

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="/workspace/$RUN_ID"
mkdir -p "$RUN_DIR/db"

cleanup() {
  rm -rf "$RUN_DIR"
}
trap cleanup EXIT INT TERM

echo "Creating application PostgreSQL dump..."
PGPASSWORD="$APP_DB_PASSWORD" pg_dump \
  --host "$APP_DB_HOST" --port "$APP_DB_PORT" \
  --username "$APP_DB_USER" --dbname "$APP_DB_NAME" \
  --format=custom --no-owner --no-privileges \
  --file "$RUN_DIR/db/application.dump"

echo "Creating PowerDNS PostgreSQL dump..."
PGPASSWORD="$PDNS_DB_PASSWORD" pg_dump \
  --host "$PDNS_DB_HOST" --port "$PDNS_DB_PORT" \
  --username "$PDNS_DB_USER" --dbname "$PDNS_DB_NAME" \
  --format=custom --no-owner --no-privileges \
  --file "$RUN_DIR/db/powerdns.dump"

AUTH_SHA=""
if [ -n "$AUTH_DB_PASSWORD" ]; then
  echo "Creating centralized !thute Auth PostgreSQL dump..."
  PGPASSWORD="$AUTH_DB_PASSWORD" pg_dump \
    --host "$AUTH_DB_HOST" --port "$AUTH_DB_PORT" \
    --username "$AUTH_DB_USER" --dbname "$AUTH_DB_NAME" \
    --format=custom --no-owner --no-privileges \
    --file "$RUN_DIR/db/ithute-auth.dump"
  AUTH_SHA="$(sha256sum "$RUN_DIR/db/ithute-auth.dump" | awk '{print $1}')"
else
  echo "Central !thute Auth backup skipped because AUTH_DB_PASSWORD is not configured."
fi

APP_SHA="$(sha256sum "$RUN_DIR/db/application.dump" | awk '{print $1}')"
PDNS_SHA="$(sha256sum "$RUN_DIR/db/powerdns.dump" | awk '{print $1}')"
MAIL_FILES="$(find /data/mail -type f 2>/dev/null | wc -l | tr -d ' ')"

if [ -n "$AUTH_SHA" ]; then
  AUTH_MANIFEST="\"identity_database\": {\"name\": \"$AUTH_DB_NAME\", \"sha256\": \"$AUTH_SHA\"},"
else
  AUTH_MANIFEST="\"identity_database\": null,"
fi

cat > "$RUN_DIR/manifest.json" <<EOF
{
  "schema_version": 2,
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "application_database": {"name": "$APP_DB_NAME", "sha256": "$APP_SHA"},
  "powerdns_database": {"name": "$PDNS_DB_NAME", "sha256": "$PDNS_SHA"},
  $AUTH_MANIFEST
  "maildir_file_count": $MAIL_FILES,
  "redis_policy": "application Redis and Rspamd signing Redis are rebuildable/ephemeral and are intentionally excluded"
}
EOF

if ! restic snapshots >/dev/null 2>&1; then
  echo "Initializing encrypted Restic repository..."
  restic init >/dev/null
fi

echo "Writing encrypted backup snapshot..."
restic backup "$RUN_DIR" /data/mail \
  --tag mailbox-dns \
  --tag phase11 \
  --tag "$RUN_ID" \
  --host mailbox-dns-backup

echo "Applying retention policy..."
restic forget \
  --tag mailbox-dns \
  --keep-daily "$BACKUP_KEEP_DAILY" \
  --keep-weekly "$BACKUP_KEEP_WEEKLY" \
  --keep-monthly "$BACKUP_KEEP_MONTHLY" \
  --prune

echo "Checking backup repository integrity..."
restic check --read-data-subset=1/20

echo "Backup completed: $RUN_ID"
