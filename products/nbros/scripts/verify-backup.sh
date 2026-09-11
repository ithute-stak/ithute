#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <backup.dump>" >&2
  exit 2
fi

BACKUP="$1"
test -s "$BACKUP"

if command -v pg_restore >/dev/null 2>&1; then
  pg_restore --list "$BACKUP" >/dev/null
else
  docker run --rm -i postgres:17-alpine pg_restore --list < "$BACKUP" >/dev/null
fi

echo "NBros backup archive is readable: $BACKUP"
