#!/usr/bin/env sh
set -eu

COMPOSE="docker compose"
TEST_COMPOSE="docker compose -f docker-compose.test.yml"

cleanup() {
  $TEST_COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[1/10] Validating development Compose configuration..."
$COMPOSE config >/dev/null

echo "[2/10] Validating production Compose configuration..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null

echo "[3/10] Rebuilding backend test image from current Phase 3 source..."
$TEST_COMPOSE build --pull backend-test

echo "[4/10] Starting disposable PostgreSQL and Redis..."
$TEST_COMPOSE up -d postgres-test redis-test

echo "[5/10] Testing fresh migration to Phase 3 head..."
$TEST_COMPOSE run --rm backend-test sh -c "alembic upgrade head"

echo "[6/10] Testing Phase 3 downgrade/upgrade lifecycle without rewriting Phase 2..."
$TEST_COMPOSE run --rm backend-test sh -c "alembic downgrade 0002 && alembic upgrade head"

echo "[7/10] Running complete backend suite including domain isolation and verification tests..."
$TEST_COMPOSE run --rm backend-test sh -c "alembic upgrade head && python -m pytest -q"

echo "[8/10] Building frontend with Tailwind domain portfolio UI..."
$TEST_COMPOSE build --pull frontend-test

echo "[9/10] Building complete production backend/frontend images..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml build --pull backend frontend

echo "[10/10] Re-validating deployment configuration..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null

echo "Phase 3 verification PASSED."
