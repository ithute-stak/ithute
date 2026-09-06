#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase5-secondary.yml"

wait_for_url() {
  name="$1"
  url="$2"
  attempts="${3:-120}"
  delay="${4:-5}"
  i=1
  while [ "$i" -le "$attempts" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    printf 'Waiting for %s readiness (%s/%s)...\n' "$name" "$i" "$attempts"
    sleep "$delay"
    i=$((i + 1))
  done
  printf '%s did not become ready at %s\n' "$name" "$url" >&2
  return 1
}

wait_for_service_healthy() {
  service="$1"
  attempts="${2:-60}"
  delay="${3:-2}"
  i=1
  while [ "$i" -le "$attempts" ]; do
    container_id="$($COMPOSE ps -q "$service" 2>/dev/null || true)"
    if [ -n "$container_id" ]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      case "$status" in
        healthy|running)
          printf '%s is ready (%s).\n' "$service" "$status"
          return 0
          ;;
        exited|dead)
          printf '%s stopped while waiting for readiness.\n' "$service" >&2
          $COMPOSE logs --tail=160 "$service" >&2 || true
          return 1
          ;;
      esac
      printf 'Waiting for %s health (%s/%s, status=%s)...\n' "$service" "$i" "$attempts" "${status:-unknown}"
    else
      printf 'Waiting for %s container (%s/%s)...\n' "$service" "$i" "$attempts"
    fi
    sleep "$delay"
    i=$((i + 1))
  done

  printf '%s did not become healthy.\n' "$service" >&2
  $COMPOSE ps "$service" >&2 || true
  $COMPOSE logs --tail=200 "$service" >&2 || true
  container_id="$($COMPOSE ps -q "$service" 2>/dev/null || true)"
  if [ -n "$container_id" ]; then
    docker inspect --format '{{json .State.Health}}' "$container_id" >&2 || true
  fi
  return 1
}

printf '\n== Phase 5: compose configuration ==\n'
$COMPOSE config >/dev/null

printf '\n== Phase 5: rebuild application images ==\n'
$COMPOSE build backend frontend

# Start infrastructure in stages. A cold GitHub runner can take several seconds
# to initialise the PowerDNS control socket after PostgreSQL becomes healthy.
# Starting backend in the same `compose up` call makes Compose evaluate its
# `service_healthy` dependency during that transition and can abort even though
# PowerDNS is still legitimately in the health-starting state.
printf '\n== Phase 5: start databases and Redis ==\n'
$COMPOSE up -d postgres redis powerdns-db powerdns-secondary-db

printf '\n== Phase 5: start authoritative DNS services ==\n'
$COMPOSE up -d powerdns powerdns-secondary
wait_for_service_healthy powerdns 60 2
wait_for_service_healthy powerdns-secondary 60 2

printf '\n== Phase 5: PowerDNS control planes ==\n'
$COMPOSE exec -T powerdns pdns_control rping | grep -q PONG
$COMPOSE exec -T powerdns-secondary pdns_control rping | grep -q PONG

printf '\n== Phase 5: start application services ==\n'
$COMPOSE up -d backend frontend

printf '\n== Phase 5: migrations ==\n'
$COMPOSE exec -T backend alembic upgrade head

printf '\n== Phase 5: backend tests ==\n'
$COMPOSE exec -T backend pytest -q

printf '\n== Phase 5: DNSSEC and secondary AXFR integration ==\n'
$COMPOSE run --rm --no-deps -v "$(pwd)/scripts:/phase5-scripts:ro" backend python /phase5-scripts/phase5-secondary-smoke.py

printf '\n== Phase 5: frontend production build ==\n'
$COMPOSE build frontend

printf '\n== Phase 5: route smoke checks ==\n'
wait_for_url backend "http://localhost:${BACKEND_PORT:-8006}/health/ready" 60 2
if ! wait_for_url frontend "http://localhost:${FRONTEND_PORT:-3006}/" 120 5; then
  $COMPOSE ps >&2 || true
  $COMPOSE logs --tail=120 frontend >&2 || true
  exit 1
fi

printf '\nPhase 5 verification PASSED.\n'
printf 'Local DNSSEC signing, DS generation, authoritative answers, secondary AXFR and refresh were verified.\n'
printf 'Production launch still requires real delegated domains and ns1/ns2 on independent public hosts.\n'
