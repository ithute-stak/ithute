#!/usr/bin/env sh
set -eu

mode="${1:-check}"
minimum_free_mb="${2:-2048}"
release_backup_keep="${ITHUTE_RELEASE_BACKUP_KEEP:-5}"

case "$mode" in
  cleanup|check) ;;
  *) echo "Usage: $0 [cleanup|check] [minimum-free-mib]" >&2; exit 2 ;;
esac

case "$minimum_free_mb" in
  ''|*[!0-9]*) echo "minimum-free-mib must be an integer" >&2; exit 2 ;;
esac
case "$release_backup_keep" in
  ''|*[!0-9]*) echo "ITHUTE_RELEASE_BACKUP_KEEP must be an integer" >&2; exit 2 ;;
esac

free_mb() {
  df -Pk . | awk 'NR == 2 { print int($4 / 1024) }'
}

show_storage() {
  echo "=== Production storage ==="
  df -h . || true
  docker system df || true
  if [ -d backups ]; then
    du -sh backups 2>/dev/null || true
  fi
}

remove_stale_staging_files() {
  find /tmp -maxdepth 1 -type f \
    \( -name 'ithute-*.tgz' \
       -o -name 'ithute-overrides-*.env' \
       -o -name 'ithute-tutor-images-*.tar.gz' \
       -o -name 'docker-compose.ithute-tutor-*.yml' \
       -o -name 'ithute-edge-tutor-*.conf' \) \
    -mmin +180 -print -delete 2>/dev/null || true
}

remove_invalid_release_backups() {
  [ -d backups ] || return 0

  # Zero-byte files are always failed deployment snapshots.
  find backups -maxdepth 1 -type f -name '*-before-*.dump' -size 0 -print -delete 2>/dev/null || true

  # A failed pg_dump can leave a non-empty partial custom-format file. Validate
  # release snapshots with pg_restore when a PostgreSQL container is available.
  pg_container="$(docker ps -q --filter label=com.docker.compose.service=postgres | head -n1 || true)"
  [ -n "$pg_container" ] || return 0

  find backups -maxdepth 1 -type f -name '*-before-*.dump' -print 2>/dev/null | while IFS= read -r file; do
    [ -s "$file" ] || continue
    if ! docker exec -i "$pg_container" pg_restore -l >/dev/null 2>&1 < "$file"; then
      echo "Removing incomplete pre-release database snapshot: $file"
      rm -f -- "$file"
    fi
  done
}

prune_release_family() {
  pattern="$1"
  keep="$2"
  [ -d backups ] || return 0

  find backups -maxdepth 1 -type f -name "$pattern" -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr \
    | awk -v keep="$keep" 'NR > keep { sub(/^[^ ]+ /, ""); print }' \
    | while IFS= read -r file; do
        [ -n "$file" ] || continue
        echo "Removing expired pre-release snapshot: $file"
        rm -f -- "$file"
      done
}

prune_expired_release_backups() {
  # These are short-lived deployment rollback snapshots only. Scheduled backup
  # repositories, database volumes, uploads/media and platform secrets are not
  # touched. Keep the newest snapshots for each database family.
  prune_release_family 'app-before-*.dump' "$release_backup_keep"
  prune_release_family 'powerdns-before-*.dump' "$release_backup_keep"
  prune_release_family 'ithute-auth-before-*.dump' "$release_backup_keep"
  prune_release_family 'ithute-push-before-*.dump' "$release_backup_keep"
  prune_release_family 'ithute-realtime-before-*.dump' "$release_backup_keep"
  prune_release_family 'ithute-tutor-before-*.dump' "$release_backup_keep"
}

if [ "$mode" = "cleanup" ]; then
  echo "Reclaiming disposable production storage. Persistent Docker volumes are never pruned."
  remove_stale_staging_files
  remove_invalid_release_backups

  # Build cache and images not referenced by running containers are disposable.
  # Never use docker system prune --volumes or docker volume prune here.
  docker builder prune -af >/dev/null 2>&1 || true
  docker image prune -af >/dev/null 2>&1 || true

  current_free_mb="$(free_mb)"
  if [ "$current_free_mb" -lt "$minimum_free_mb" ]; then
    echo "Free space is ${current_free_mb} MiB; applying pre-release snapshot retention (keep ${release_backup_keep} per database)."
    prune_expired_release_backups
  fi
fi

show_storage
current_free_mb="$(free_mb)"
if [ "$current_free_mb" -lt "$minimum_free_mb" ]; then
  echo "Production storage preflight failed: ${current_free_mb} MiB free, ${minimum_free_mb} MiB required." >&2
  echo "No persistent volume or live database data was deleted." >&2
  exit 1
fi

echo "Production storage preflight passed: ${current_free_mb} MiB free (minimum ${minimum_free_mb} MiB)."
