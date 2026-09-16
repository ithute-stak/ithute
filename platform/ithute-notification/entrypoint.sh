#!/bin/sh
set -eu

case "${1:-api}" in
  api)
    exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers
    ;;
  worker)
    exec python -m app.worker
    ;;
  *)
    exec "$@"
    ;;
esac
