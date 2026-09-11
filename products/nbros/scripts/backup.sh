#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${NBROS_COMPOSE_FILE:-${ROOT_DIR}/compose.yaml}"
BACKUP_DIR="${NBROS_BACKUP_DIR:-${ROOT_DIR}/backups}"
DB_USER="${NBROS_DB_USER:-nbros}"
DB_NAME="${NBROS_DB_NAME:-nbros}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT="${1:-${BACKUP_DIR}/nbros-${STAMP}.dump}"

mkdir -p "$(dirname "${OUTPUT}")"
umask 077

docker compose -f "${COMPOSE_FILE}" exec -T db \
  pg_dump -U "${DB_USER}" -d "${DB_NAME}" --format=custom --no-owner --no-privileges > "${OUTPUT}"

test -s "${OUTPUT}"
printf 'NBros PostgreSQL backup created: %s\n' "${OUTPUT}"
