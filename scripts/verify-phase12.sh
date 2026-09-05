#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml -f docker-compose.phase12-monitoring.yml"

wait_for_backend_ready() {
  attempts=0
  max_attempts=45
  until $COMPOSE exec -T backend curl -fsS http://127.0.0.1:8000/health/ready >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$max_attempts" ]; then
      printf 'Backend did not become ready after %s attempts.\n' "$max_attempts" >&2
      $COMPOSE ps backend >&2 || true
      $COMPOSE logs --no-color --tail=200 backend >&2 || true
      exit 1
    fi
    sleep 2
  done
  printf 'Backend readiness confirmed.\n'
}

wait_for_service_http() {
  service="$1"
  url="$2"
  attempts=0
  max_attempts=45
  until $COMPOSE exec -T "$service" wget -qO- "$url" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$max_attempts" ]; then
      printf '%s did not become ready at %s after %s attempts.\n' "$service" "$url" "$max_attempts" >&2
      $COMPOSE ps "$service" >&2 || true
      $COMPOSE logs --no-color --tail=200 "$service" >&2 || true
      exit 1
    fi
    sleep 2
  done
  printf '%s readiness confirmed.\n' "$service"
}

wait_for_ops_exporter() {
  attempts=0
  max_attempts=45
  until $COMPOSE exec -T ops-exporter python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:9108/healthz', timeout=3); assert r.status == 200; assert r.read().strip() == b'ok'" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$max_attempts" ]; then
      printf 'ops-exporter did not become ready after %s attempts.\n' "$max_attempts" >&2
      $COMPOSE ps ops-exporter >&2 || true
      $COMPOSE logs --no-color --tail=200 ops-exporter >&2 || true
      exit 1
    fi
    sleep 2
  done
  printf 'ops-exporter readiness confirmed.\n'
}

probe_expect_success() {
  name="$1"
  module="$2"
  target="$3"
  attempts="${4:-20}"
  delay="${5:-2}"
  i=1
  output=""

  while [ "$i" -le "$attempts" ]; do
    output="$($COMPOSE exec -T prometheus wget -qO- "http://blackbox-exporter:9115/probe?module=${module}&target=${target}" 2>/dev/null || true)"
    if printf '%s\n' "$output" | grep -q '^probe_success 1$'; then
      printf '%s synthetic probe PASSED (%s -> %s).\n' "$name" "$module" "$target"
      return 0
    fi
    printf 'Waiting for %s synthetic probe (%s/%s)...\n' "$name" "$i" "$attempts"
    sleep "$delay"
    i=$((i + 1))
  done

  printf '%s synthetic probe FAILED (%s -> %s).\n' "$name" "$module" "$target" >&2
  printf '%s\n' "$output" >&2
  $COMPOSE logs --tail=80 blackbox-exporter >&2 || true
  return 1
}

printf '\n== Phase 12: Phase 11 regression gate ==\n'
sh scripts/verify-phase11.sh

printf '\n== Phase 12: rebuild instrumented backend ==\n'
$COMPOSE build backend
$COMPOSE up -d --force-recreate backend
wait_for_backend_ready

printf '\n== Phase 12: application metrics endpoint and operations unit coverage ==\n'
$COMPOSE exec -T backend pytest -q tests/test_operations_status.py
$COMPOSE exec -T backend python - <<'PY'
import httpx
base = 'http://127.0.0.1:8000'
with httpx.Client(base_url=base, timeout=5) as client:
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 200
    response = client.get('/metrics')
    assert response.status_code == 200
    text = response.text
    assert 'mailbox_dns_http_requests_total' in text
    assert 'mailbox_dns_http_request_duration_seconds' in text
    assert 'mailbox_dns_dependency_ready' in text
    schema = client.get('/openapi.json').json()
    assert '/api/v1/operations/status' in schema['paths']
    assert '/api/v1/operations/slo' in schema['paths']
print('application metrics and platform-owner operations routes verified')
PY

printf '\n== Phase 12: Prometheus, alert, and blackbox config ==\n'
$COMPOSE run --rm --no-deps --entrypoint /bin/promtool prometheus check config /etc/prometheus/prometheus.yml
$COMPOSE run --rm --no-deps --entrypoint /bin/promtool prometheus check rules /etc/prometheus/alert-rules.yml
$COMPOSE run --rm --no-deps blackbox-exporter --config.check --config.file=/etc/blackbox_exporter/config.yml

printf '\n== Phase 12: authoritative DNS monitoring canary ==\n'
$COMPOSE exec -T backend python - <<'PY'
from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

api = os.environ.get('POWERDNS_API_URL', 'http://powerdns:8081/api/v1').rstrip('/')
api_key = os.environ.get('POWERDNS_API_KEY', 'development-powerdns-api-key-change-me')
server = os.environ.get('POWERDNS_SERVER_ID', 'localhost')
zone = 'phase12-monitor.test.'
server_id = quote(server, safe='')
zone_id = quote(zone, safe='')
headers = {
    'X-API-Key': api_key,
    'Accept': 'application/json',
    'Content-Type': 'application/json',
}


def request(method: str, path: str, payload=None, expected=(200, 201, 204)):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(api + path, data=body, method=method, headers=headers)
    with urlopen(req, timeout=8) as response:
        if response.status not in expected:
            raise RuntimeError(f'unexpected PowerDNS HTTP {response.status} for {method} {path}')
        raw = response.read()
        return json.loads(raw) if raw else None


zone_path = f'/servers/{server_id}/zones/{zone_id}'
try:
    request('GET', zone_path, expected=(200,))
    print(f'authoritative DNS monitoring canary already exists: {zone}')
except HTTPError as exc:
    if exc.code != 404:
        detail = exc.read().decode(errors='replace')
        raise RuntimeError(f'PowerDNS HTTP {exc.code} while checking monitoring canary: {detail}') from exc
    request(
        'POST',
        f'/servers/{server_id}/zones',
        {
            'name': zone,
            'kind': 'Master',
            'nameservers': ['ns1.phase12-monitor.test.', 'ns2.phase12-monitor.test.'],
            'api_rectify': True,
        },
        expected=(201,),
    )
    print(f'authoritative DNS monitoring canary created: {zone}')
PY

printf '\n== Phase 12: monitoring and operations stack ==\n'
$COMPOSE up -d alertmanager blackbox-exporter ops-exporter prometheus grafana node-exporter cadvisor
wait_for_service_http alertmanager http://localhost:9093/-/ready
wait_for_service_http blackbox-exporter http://localhost:9115/metrics
wait_for_ops_exporter
wait_for_service_http prometheus http://localhost:9090/-/ready
$COMPOSE exec -T prometheus wget -qO- http://localhost:9090/-/ready >/dev/null
$COMPOSE exec -T alertmanager wget -qO- http://localhost:9093/-/ready >/dev/null

printf '\n== Phase 12: queue and backup exporter ==\n'
$COMPOSE exec -T ops-exporter python - <<'PY'
import urllib.request

with urllib.request.urlopen('http://127.0.0.1:9108/metrics', timeout=10) as response:
    assert response.status == 200
    text = response.read().decode()

assert 'mailbox_dns_mail_queue_total' in text
assert 'mailbox_dns_backup_last_run_success' in text
print('ops-exporter queue and backup metrics verified')
PY

printf '\n== Phase 12: SMTP, IMAP, and DNS synthetic probes ==\n'
probe_expect_success 'SMTP' 'smtp_banner' 'postfix:25'
probe_expect_success 'IMAP' 'imap_banner' 'dovecot:143'
probe_expect_success 'DNS' 'dns_authoritative' 'powerdns:53'

printf '\n== Phase 12: Prometheus target/query visibility and operations service ==\n'
$COMPOSE exec -T prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=up%7Bjob%3D%22mailbox-dns-backend%22%7D' | grep -q '"status":"success"'
$COMPOSE exec -T prometheus wget -qO- 'http://localhost:9090/api/v1/query?query=mailbox_dns_mail_queue_total' | grep -q '"status":"success"'
$COMPOSE exec -T backend python - <<'PY'
from app.services.operations_status import operations_status, slo_status
status = operations_status()
slo = slo_status()
assert status['status'] in {'ok', 'degraded'}
assert {'backend', 'smtp', 'imap', 'authoritative_dns', 'backup'} <= set(status['services'])
assert slo['window'] == '7d'
assert slo['target'] == 0.999
print('live Prometheus-backed operations and SLO service verified')
PY

printf '\n== Phase 12: SLO/error-budget rules and richer alert metadata ==\n'
grep -q 'mailbox_dns:slo_availability_7d' infra/monitoring/alert-rules.yml
grep -q 'mailbox_dns:slo_error_budget_remaining_7d' infra/monitoring/alert-rules.yml
grep -q 'mailbox_dns:slo_burn_rate_1h' infra/monitoring/alert-rules.yml
grep -q 'operator_action:' infra/monitoring/alert-rules.yml
grep -q 'runbook:' infra/monitoring/alert-rules.yml
grep -q 'component:' infra/monitoring/alert-rules.yml

printf '\n== Phase 12: dashboards, routing, runbooks, and production boundary ==\n'
$COMPOSE config --services | grep -qx alertmanager
$COMPOSE config --services | grep -qx blackbox-exporter
$COMPOSE config --services | grep -qx ops-exporter
$COMPOSE config | grep -q 'PROMETHEUS_URL'
$COMPOSE config | grep -q 'OPERATIONS_SLO_TARGET'
grep -q 'url: http://prometheus:9090' infra/monitoring/grafana-datasources.yml
grep -q 'Mailbox DNS Operations' infra/monitoring/mailbox-dns-operations.json
grep -q 'Mailbox DNS SLO & Error Budget' infra/monitoring/mailbox-dns-slo.json
grep -q 'alertmanagers:' infra/monitoring/prometheus.yml
test -s docs/PHASE-12-INCIDENT-OPERATIONS.md
grep -q 'Triage order' docs/PHASE-12-INCIDENT-OPERATIONS.md
test -s docs/PHASE-12-MONITORING-OPERATIONS.md
grep -q 'Platform-owner operations API' docs/PHASE-12-MONITORING-OPERATIONS.md
grep -q 'does not constitute a contractual SLA' docs/PHASE-12-MONITORING-OPERATIONS.md

printf '\nPhase 12 FINAL MONITORING & OPERATIONS acceptance PASSED.\n'
printf 'Verified full Phase 11 regression, Prometheus instrumentation, SMTP/IMAP/DNS synthetic probes, Postfix queue and backup telemetry, Alertmanager routing, host/container exporters, provisioned operations and SLO dashboards, platform-owner operations status APIs, seven-day availability/error-budget recording rules, richer alert runbook metadata, and incident operations guidance.\n'
printf 'Phase 12 is ready for acceptance and fast-forward convergence to main after user confirmation.\n'
