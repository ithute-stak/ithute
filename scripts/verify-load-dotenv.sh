#!/usr/bin/env sh
set -eu

repo_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

cat > "$tmp/docker" <<'SH'
#!/usr/bin/env sh
set -eu
# load_dotenv only needs Docker Compose's parsed environment output for this
# regression test. Include values with embedded and trailing equals signs.
printf '%s\n' \
  'ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=' \
  'EMBEDDED_EQUALS=a=b=c' \
  'EMPTY_VALUE='
SH
chmod +x "$tmp/docker"
: > "$tmp/test.env"

PATH="$tmp:$PATH"
export PATH

. "$repo_dir/scripts/load-dotenv.sh"
load_dotenv "$tmp/test.env"

expected_fernet='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY='
[ "${ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY:-}" = "$expected_fernet" ] || {
  echo "load-dotenv regression: trailing '=' padding was not preserved" >&2
  exit 1
}
[ "${EMBEDDED_EQUALS:-}" = 'a=b=c' ] || {
  echo "load-dotenv regression: embedded '=' characters were not preserved" >&2
  exit 1
}
[ "${EMPTY_VALUE+x}" = x ] && [ -z "${EMPTY_VALUE}" ] || {
  echo "load-dotenv regression: empty value was not preserved" >&2
  exit 1
}

echo "load-dotenv verification passed."
