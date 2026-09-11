#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"

echo "== NBros backend syntax =="
cd "$ROOT/apps/backend"
python -m compileall -q app alembic tests

if command -v pytest >/dev/null 2>&1; then
  echo "== NBros Fleet tests =="
  pytest -q --maxfail=1
else
  echo "pytest is not installed; install requirements-dev.txt to run Fleet tests."
fi

echo "== NBros frontend checks =="
cd "$ROOT/apps/frontend"
if [ -d node_modules ]; then
  npm run typecheck
  npm run build
else
  echo "node_modules is missing; run npm install first."
fi

echo "== NBros Compose contract =="
cd "$ROOT"
if command -v docker >/dev/null 2>&1; then
  : "${NBROS_DB_PASSWORD:=nbros-local-validation-password}"
  export NBROS_DB_PASSWORD
  docker compose -f compose.yaml config -q
else
  echo "docker is not installed; Compose validation skipped."
fi
