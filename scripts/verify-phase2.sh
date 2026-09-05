#!/usr/bin/env sh
set -eu

COMPOSE="docker compose"
TEST_COMPOSE="docker compose -f docker-compose.test.yml"

cleanup() {
  $TEST_COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[1/9] Validating development Compose configuration..."
$COMPOSE config >/dev/null

echo "[2/9] Validating production Compose configuration..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null

echo "[3/9] Rebuilding backend test image from current Phase 2 source..."
$TEST_COMPOSE build --pull backend-test

echo "[4/9] Starting disposable PostgreSQL and Redis..."
$TEST_COMPOSE up -d postgres-test redis-test

echo "[5/9] Testing Phase 2 migration upgrade/downgrade/upgrade lifecycle..."
$TEST_COMPOSE run --rm backend-test sh -c "alembic upgrade head && alembic downgrade 0001 && alembic upgrade head"

echo "[6/9] Running complete backend integration suite..."
$TEST_COMPOSE run --rm backend-test sh -c "alembic upgrade head && python -m pytest -q"

echo "[7/9] Building production frontend with Phase 2 identity UI..."
$TEST_COMPOSE build --pull frontend-test

echo "[8/9] Building complete production backend/frontend images..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml build --pull backend frontend

echo "[9/9] Re-validating deployment configuration..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null

echo "Phase 2 verification PASSED."
