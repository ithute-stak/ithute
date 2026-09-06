#!/bin/sh
set -eu

case "${1:-api}" in
  api)
    alembic upgrade head
    python -m app.system_owner
    exec uvicorn app.server:app --host 0.0.0.0 --port 8080
    ;;
  push-event-worker)
    exec python -m app.push_event_worker
    ;;
  *)
    exec "$@"
    ;;
esac
