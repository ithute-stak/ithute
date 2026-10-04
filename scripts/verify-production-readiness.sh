#!/usr/bin/env bash
set -euo pipefail

PUBLIC_URL="${ITHUTE_PUBLIC_URL:-https://ithute.co.ls}"
AUTH_URL="${ITHUTE_AUTH_URL:-https://auth.ithute.co.ls}"
PUSH_URL="${ITHUTE_PUSH_URL:-https://push.ithute.co.ls}"
REALTIME_URL="${ITHUTE_REALTIME_URL:-https://realtime.ithute.co.ls}"
PUBLIC_IPV4="${ITHUTE_PUBLIC_IPV4:-204.12.205.224}"
MAIL_HOST="${ITHUTE_MAIL_HOST:-mail.ithute.co.ls}"
REQUIRE_PTR="${ITHUTE_REQUIRE_PTR:-false}"
REQUIRE_INDEPENDENT_DNS="${ITHUTE_REQUIRE_INDEPENDENT_DNS:-false}"
HOSTED_TEST_DOMAIN="${ITHUTE_TEST_HOSTED_DOMAIN:-}"
COMPOSE_FILE="${ITHUTE_COMPOSE_FILE:-compose.production.yml}"
ENV_FILE="${ITHUTE_ENV_FILE:-.env.production}"

failures=0
warnings=0

pass() { printf 'PASS  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*" >&2; warnings=$((warnings + 1)); }
fail() { printf 'FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Required command is unavailable: $1"
    return 1
  fi
}

check_url() {
  local label="$1" url="$2" expected_header="${3:-}"
  local headers body
  headers="$(mktemp)"; body="$(mktemp)"
  if curl --fail --silent --show-error --location --max-time 15 --dump-header "$headers" --output "$body" "$url"; then
    if [[ -n "$expected_header" ]] && ! tr -d '\r' < "$headers" | grep -Fqi "$expected_header"; then
      fail "$label responded but did not expose expected routing header: $expected_header"
    else
      pass "$label: $url"
    fi
  else
    fail "$label is not healthy: $url"
  fi
  rm -f "$headers" "$body"
}

require_command curl || true
require_command python3 || true
require_command dig || true

if command -v curl >/dev/null 2>&1; then
  check_url "Ithute web" "$PUBLIC_URL/health" "X-Ithute-Service: web"
  check_url "Ithute application API" "$PUBLIC_URL/openapi.json" "X-Ithute-Service: app-api"
  check_url "Ithute Auth" "$AUTH_URL/healthz" "X-Ithute-Service: auth"
  check_url "Ithute Push" "$PUSH_URL/readyz" "X-Ithute-Service: push"
  check_url "Ithute Realtime" "$REALTIME_URL/readyz" "X-Ithute-Service: realtime"
fi

if command -v python3 >/dev/null 2>&1; then
  if python3 "$(dirname "$0")/verify-authoritative-dns.py" --server "$PUBLIC_IPV4" --expected-ip "$PUBLIC_IPV4"; then
    pass "Authoritative Ithute DNS responds correctly over UDP and TCP"
  else
    fail "Authoritative Ithute DNS verification failed"
  fi
fi

if command -v dig >/dev/null 2>&1; then
  mx="$(dig +short MX ithute.co.ls | tr '[:upper:]' '[:lower:]')"
  if grep -Eq "[[:space:]]${MAIL_HOST//./\.}\.?$" <<<"$mx"; then pass "ithute.co.ls MX points to $MAIL_HOST"; else fail "ithute.co.ls MX does not point to $MAIL_HOST (got: ${mx:-none})"; fi

  spf="$(dig +short TXT ithute.co.ls | tr -d '"')"
  if grep -Fqi 'v=spf1' <<<"$spf"; then pass "SPF record is published"; else fail "SPF record is missing"; fi

  dmarc="$(dig +short TXT _dmarc.ithute.co.ls | tr -d '"')"
  if grep -Fqi 'v=DMARC1' <<<"$dmarc"; then pass "DMARC record is published"; else fail "DMARC record is missing"; fi

  ns1_ips="$(dig +short A ns1.ithute.co.ls | sort -u)"
  ns2_ips="$(dig +short A ns2.ithute.co.ls | sort -u)"
  if [[ -z "$ns1_ips" || -z "$ns2_ips" ]]; then
    fail "ns1/ns2 public A records are incomplete"
  elif [[ "$ns1_ips" == "$ns2_ips" ]]; then
    if [[ "$REQUIRE_INDEPENDENT_DNS" == "true" ]]; then fail "ns1 and ns2 resolve to the same address; independent secondary DNS is required"; else warn "ns1 and ns2 resolve to the same address ($ns1_ips). DNS works, but this is not infrastructure redundancy."; fi
  else
    pass "ns1 and ns2 resolve to independent address sets"
  fi

  ptr="$(dig +short -x "$PUBLIC_IPV4" | sed 's/\.$//' | tr '[:upper:]' '[:lower:]' | head -n1)"
  expected_ptr="${MAIL_HOST%.}"
  if [[ "$ptr" == "$expected_ptr" ]]; then pass "PTR/reverse DNS identifies $MAIL_HOST"; elif [[ "$REQUIRE_PTR" == "true" ]]; then fail "PTR for $PUBLIC_IPV4 must be $MAIL_HOST (got: ${ptr:-none})"; else warn "PTR for $PUBLIC_IPV4 is '${ptr:-none}', expected '$MAIL_HOST'. This must be corrected by the VPS/IP provider."; fi

  if [[ -n "$HOSTED_TEST_DOMAIN" ]]; then
    route_ips="$(dig +short A "$HOSTED_TEST_DOMAIN" | sort -u)"
    if grep -Fxq "$PUBLIC_IPV4" <<<"$route_ips"; then
      pass "$HOSTED_TEST_DOMAIN has propagated to Ithute edge $PUBLIC_IPV4"
      check_url "Hosted customer route" "https://$HOSTED_TEST_DOMAIN/"
    else
      fail "$HOSTED_TEST_DOMAIN has not propagated to Ithute edge $PUBLIC_IPV4 (got: ${route_ips:-none})"
    fi
  else
    warn "ITHUTE_TEST_HOSTED_DOMAIN is unset; live customer-domain Caddy/TLS route was not exercised"
  fi
fi

if [[ -f "$ENV_FILE" ]] && grep -q '^ITHUTE_WIREGUARD_EDGE_PUBLIC_KEY=' "$ENV_FILE"; then
  wg_public="$(sed -n 's/^ITHUTE_WIREGUARD_EDGE_PUBLIC_KEY=//p' "$ENV_FILE" | tail -n1)"
  wg_address="$(sed -n 's/^ITHUTE_WIREGUARD_EDGE_ADDRESS=//p' "$ENV_FILE" | tail -n1)"
  wg_port="$(sed -n 's/^ITHUTE_WIREGUARD_LISTEN_PORT=//p' "$ENV_FILE" | tail -n1)"
  wg_endpoint="$(sed -n 's/^ITHUTE_WIREGUARD_EDGE_ENDPOINT=//p' "$ENV_FILE" | tail -n1)"

  require_command wg || true
  require_command ip || true
  require_command systemctl || true

  if command -v wg >/dev/null 2>&1 && command -v ip >/dev/null 2>&1; then
    if ip link show ithute0 >/dev/null 2>&1; then pass "Managed private-network interface ithute0 exists"; else fail "Managed private-network interface ithute0 is missing"; fi
    if [[ -n "$wg_address" ]] && ip -4 -o addr show dev ithute0 2>/dev/null | grep -Fq " $wg_address/"; then pass "ithute0 owns configured edge address $wg_address"; else fail "ithute0 does not own configured edge address ${wg_address:-unset}"; fi
    actual_public="$(wg show ithute0 public-key 2>/dev/null || true)"
    if [[ -n "$wg_public" && "$actual_public" == "$wg_public" ]]; then pass "WireGuard edge public key matches production configuration"; else fail "WireGuard edge public key does not match production configuration"; fi
    actual_port="$(wg show ithute0 listen-port 2>/dev/null || true)"
    if [[ -n "$wg_port" && "$actual_port" == "$wg_port" ]]; then pass "WireGuard edge is listening on configured UDP port $wg_port"; else fail "WireGuard edge listen port does not match production configuration"; fi
  fi

  if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet ithute-wireguard-edge-firewall.service; then pass "WireGuard edge firewall service is active"; else fail "ithute-wireguard-edge-firewall.service is not active"; fi
    if systemctl is-active --quiet wg-quick@ithute0; then pass "WireGuard edge interface service is active"; else fail "wg-quick@ithute0 is not active"; fi
    if systemctl is-active --quiet ithute-wireguard-edge-reconciler.timer; then pass "WireGuard peer reconciler timer is active"; else fail "WireGuard peer reconciler timer is not active"; fi
  fi

  if [[ -s /etc/ithute-wireguard/reconciler.env ]]; then pass "Private-network reconciler credential file exists"; else fail "Private-network reconciler credential file is missing"; fi
  if [[ "$wg_endpoint" == "$PUBLIC_IPV4:$wg_port" ]]; then pass "WireGuard advertised endpoint matches Ithute public edge"; else fail "WireGuard advertised endpoint is '${wg_endpoint:-unset}', expected '$PUBLIC_IPV4:${wg_port:-unset}'"; fi
fi

if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
  if docker compose -f "$COMPOSE_FILE" config >/dev/null; then pass "Production Compose renders successfully"; else fail "Production Compose does not render"; fi

  if docker compose -f "$COMPOSE_FILE" port caddy 2019 2>/dev/null | grep -q .; then
    fail "Caddy admin port 2019 is published to the host; it must remain private"
  else
    pass "Caddy admin port 2019 is not host-published"
  fi

  if docker compose -f "$COMPOSE_FILE" config --services 2>/dev/null | grep -Fxq ithute-hosting-health-controller; then
    if docker compose -f "$COMPOSE_FILE" ps --status running ithute-hosting-health-controller 2>/dev/null | grep -q ithute-hosting-health-controller; then
      pass "Hosting node self-healing controller is running"
    else
      fail "Hosting node self-healing controller is not running"
    fi
  fi

  if docker compose -f "$COMPOSE_FILE" ps --status running caddy 2>/dev/null | grep -q caddy; then
    if docker compose -f "$COMPOSE_FILE" exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
      pass "Running Caddy configuration validates"
    else
      fail "Running Caddy configuration validation failed"
    fi
  else
    warn "Caddy container is not running in this execution context; runtime config validation was skipped"
  fi

  rendered="$(docker compose -f "$COMPOSE_FILE" config 2>/dev/null || true)"
  if grep -q 'caddy_routes' <<<"$rendered"; then pass "Dynamic Caddy route volume is present in production topology"; else fail "Dynamic Caddy route volume is missing from production topology"; fi
else
  warn "Docker/production compose unavailable; container-level Caddy checks were not executed"
fi

printf '\nReadiness result: %d failure(s), %d warning(s).\n' "$failures" "$warnings"
if (( failures > 0 )); then
  exit 1
fi
