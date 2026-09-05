#!/bin/sh
set -eu

case "${1:-api}" in
  api)
    alembic upgrade head
    exec uvicorn app.combined:app --host 0.0.0.0 --port 8080
    ;;
  worker)
    exec python -m app.worker
    ;;
  *)
    exec "$@"
    ;;
esac
