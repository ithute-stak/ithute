#!/usr/bin/env sh
set -eu

COMPOSE="docker compose"
TEST_COMPOSE="docker compose -f docker-compose.test.yml"

cleanup() {
  $TEST_COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[1/8] Validating development Compose configuration..."
$COMPOSE config >/dev/null

echo "[2/8] Validating production Compose configuration..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null

echo "[3/8] Validating test Compose configuration..."
$TEST_COMPOSE config >/dev/null

echo "[4/8] Rebuilding backend test image from current source..."
$TEST_COMPOSE build --pull backend-test

echo "[5/8] Running backend migrations and integration tests in disposable PostgreSQL/Redis..."
$TEST_COMPOSE run --rm backend-test

echo "[6/8] Building the production frontend image..."
$TEST_COMPOSE build --pull frontend-test

echo "[7/8] Building the complete production application images..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml build --pull backend frontend

echo "[8/8] Checking that production images are buildable and Compose is deployment-ready..."
$COMPOSE -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null

echo "Phase 1 verification PASSED."
