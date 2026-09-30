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
  if grep -Eq "[[:space:]]${MAIL_HOST//./\.}\.?$" <<<"$mx"; then
    pass "ithute.co.ls MX points to $MAIL_HOST"
  else
    fail "ithute.co.ls MX does not point to $MAIL_HOST (got: ${mx:-none})"
  fi

  spf="$(dig +short TXT ithute.co.ls | tr -d '"')"
  if grep -Fqi 'v=spf1' <<<"$spf"; then pass "SPF record is published"; else fail "SPF record is missing"; fi

  dmarc="$(dig +short TXT _dmarc.ithute.co.ls | tr -d '"')"
  if grep -Fqi 'v=DMARC1' <<<"$dmarc"; then pass "DMARC record is published"; else fail "DMARC record is missing"; fi

  ns1_ips="$(dig +short A ns1.ithute.co.ls | sort -u)"
  ns2_ips="$(dig +short A ns2.ithute.co.ls | sort -u)"
  if [[ -z "$ns1_ips" || -z "$ns2_ips" ]]; then
    fail "ns1/ns2 public A records are incomplete"
  elif [[ "$ns1_ips" == "$ns2_ips" ]]; then
    if [[ "$REQUIRE_INDEPENDENT_DNS" == "true" ]]; then
      fail "ns1 and ns2 resolve to the same address; independent secondary DNS is required"
    else
      warn "ns1 and ns2 resolve to the same address ($ns1_ips). DNS works, but this is not infrastructure redundancy."
    fi
  else
    pass "ns1 and ns2 resolve to independent address sets"
  fi

  ptr="$(dig +short -x "$PUBLIC_IPV4" | sed 's/\.$//' | tr '[:upper:]' '[:lower:]' | head -n1)"
  expected_ptr="${MAIL_HOST%.}"
  if [[ "$ptr" == "$expected_ptr" ]]; then
    pass "PTR/reverse DNS identifies $MAIL_HOST"
  elif [[ "$REQUIRE_PTR" == "true" ]]; then
    fail "PTR for $PUBLIC_IPV4 must be $MAIL_HOST (got: ${ptr:-none})"
  else
    warn "PTR for $PUBLIC_IPV4 is '${ptr:-none}', expected '$MAIL_HOST'. This must be corrected by the VPS/IP provider."
  fi
fi

printf '\nReadiness result: %d failure(s), %d warning(s).\n' "$failures" "$warnings"
if (( failures > 0 )); then
  exit 1
fi
