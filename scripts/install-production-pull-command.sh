#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_PATH="${ITHUTE_PULL_INSTALL_PATH:-/usr/local/bin/pull}"
REPO="ithute-stak/ithute"
API="https://api.github.com/repos/$REPO"
RAW="https://raw.githubusercontent.com/$REPO"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo/root so it can write $INSTALL_PATH." >&2
  exit 2
fi

tmpdir="$(mktemp -d /tmp/ithute-pull-install.XXXXXX)"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

cat > "$tmpdir/pull" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail

product="${1:-}"
release="${2:-}"

if [ "$release" != "latest" ] || [ "$#" -ne 2 ]; then
  echo "Usage: pull {ithute|loanhub} latest" >&2
  exit 2
fi

case "$product" in
  ithute)
    REPO="ithute-stak/ithute"
    HELPER_PATH="scripts/deploy-production-latest.sh"
    HELPER_NAME="deploy-production-latest.sh"
    PREFIX="Ithute"
    ;;
  loanhub)
    REPO="ithute-stak/LoanHub"
    HELPER_PATH="scripts/deploy-production-manual.sh"
    HELPER_NAME="deploy-production-manual.sh"
    PREFIX="LoanHub"
    ;;
  *)
    echo "Usage: pull {ithute|loanhub} latest" >&2
    exit 2
    ;;
esac

API="https://api.github.com/repos/$REPO"
RAW="https://raw.githubusercontent.com/$REPO"
tmpdir="$(mktemp -d "/tmp/${product}-pull.XXXXXX")"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

curl --retry 5 --retry-delay 2 --retry-all-errors -fsSL "$API/branches/main" -o "$tmpdir/main.json"
MAIN_SHA="$(python3 - "$tmpdir/main.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
sha = data.get("commit", {}).get("sha", "")
if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
    raise SystemExit("GitHub did not return a valid 40-character main SHA")
print(sha)
PY
)"

helper="$tmpdir/$HELPER_NAME"
echo "[$PREFIX] Refreshing exact production launcher at $MAIN_SHA"
curl --retry 5 --retry-delay 2 --retry-all-errors -fsSL \
  "$RAW/$MAIN_SHA/$HELPER_PATH" \
  -o "$helper"
test -s "$helper" || { echo "Downloaded $PREFIX production launcher is empty." >&2; exit 1; }
bash -n "$helper"
chmod 700 "$helper"

case "$product" in
  ithute)
    exec bash "$helper"
    ;;
  loanhub)
    if [ "$(id -u)" -ne 0 ]; then
      echo "[LoanHub] Elevating production deployment launcher"
      exec sudo bash "$helper" latest
    fi
    exec bash "$helper" latest
    ;;
esac
SH

chmod 755 "$tmpdir/pull"
install -m 755 "$tmpdir/pull" "$INSTALL_PATH"
echo "[Production] Installed evergreen production pull launcher at $INSTALL_PATH"
echo "[Production] Supported commands:"
echo "  pull ithute latest"
echo "  pull loanhub latest"
echo "[Production] Each launcher is refreshed from that repository's exact current main SHA on every invocation."
