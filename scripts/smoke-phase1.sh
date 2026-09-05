#!/usr/bin/env sh
set -eu

FRONTEND_PORT="${FRONTEND_PORT:-3006}"
BACKEND_PORT="${BACKEND_PORT:-8006}"
BACKEND="http://localhost:${BACKEND_PORT}"
FRONTEND="http://localhost:${FRONTEND_PORT}"

wait_for() {
  url="$1"
  name="$2"
  attempts=60
  while [ "$attempts" -gt 0 ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready: $url"
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 2
  done
  echo "$name did not become ready: $url" >&2
  return 1
}

wait_for "$BACKEND/health/live" "Backend liveness"
wait_for "$BACKEND/health/ready" "Backend readiness"
wait_for "$FRONTEND" "Frontend"

curl -fsS "$BACKEND/openapi.json" >/dev/null

echo "Phase 1 runtime smoke test PASSED on frontend :${FRONTEND_PORT} and backend :${BACKEND_PORT}."
