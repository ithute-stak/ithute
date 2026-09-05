#!/usr/bin/env sh
set -eu

case "${1:-api}" in
  api)
    alembic upgrade head
    api_pid=""
    python -m app.worker &
    worker_pid=$!
    cleanup() {
      if [ -n "$api_pid" ]; then
        kill "$api_pid" >/dev/null 2>&1 || true
      fi
      kill "$worker_pid" >/dev/null 2>&1 || true
      if [ -n "$api_pid" ]; then
        wait "$api_pid" >/dev/null 2>&1 || true
      fi
      wait "$worker_pid" >/dev/null 2>&1 || true
    }
    trap cleanup EXIT INT TERM
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*' &
    api_pid=$!
    wait "$api_pid"
    ;;
  worker)
    exec python -m app.worker
    ;;
  *)
    exec "$@"
    ;;
esac
