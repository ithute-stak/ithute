#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
REPO="ithute-stak/ithute"
API="https://api.github.com/repos/$REPO"
REPO_RAW="https://raw.githubusercontent.com/$REPO"

if [ "$APP_DIR" != "/home/administrator/ithute-platform" ]; then
  echo "Refusing to operate outside /home/administrator/ithute-platform." >&2
  exit 2
fi

tmpdir="$(mktemp -d /tmp/ithute-latest.XXXXXX)"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

echo "[Ithute] Resolving current main commit"
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

echo "[Ithute] Current main: $MAIN_SHA"

REMOTE_HELPER="$tmpdir/deploy-production-manual.sh"
echo "[Ithute] Refreshing deployment helper from approved main $MAIN_SHA"
curl --retry 5 --retry-delay 2 --retry-all-errors -fsSL \
  "$REPO_RAW/$MAIN_SHA/scripts/deploy-production-manual.sh" \
  -o "$REMOTE_HELPER"
test -s "$REMOTE_HELPER" || { echo "Downloaded deployment helper is empty." >&2; exit 1; }
bash -n "$REMOTE_HELPER"
chmod 700 "$REMOTE_HELPER"

current=""
if [ -f "$APP_DIR/.image.env" ]; then
  current="$(sed -n 's/^ITHUTE_IMAGE_TAG=//p' "$APP_DIR/.image.env" | tail -n1)"
fi

if [ "$current" = "$MAIN_SHA" ]; then
  echo "[Ithute] Production is already running the latest main release; nothing to do."
  exit 0
fi

check_workflow() {
  local workflow="$1"
  local label="$2"
  local output="$tmpdir/${workflow}.json"

  curl --retry 5 --retry-delay 2 --retry-all-errors -fsSL \
    "$API/actions/workflows/$workflow/runs?branch=main&per_page=100" \
    -o "$output"

  python3 - "$MAIN_SHA" "$output" "$label" <<'PY'
import json
import sys

sha, path, label = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    runs = json.load(handle).get("workflow_runs", [])
matching = [run for run in runs if run.get("head_sha") == sha and run.get("head_branch") == "main"]
matching.sort(key=lambda run: run.get("created_at") or "", reverse=True)
if not matching:
    raise SystemExit(f"[Ithute] {label} has no run for current main {sha}")
run = matching[0]
status = run.get("status")
conclusion = run.get("conclusion")
url = run.get("html_url") or ""
print(f"[Ithute] {label}: status={status} conclusion={conclusion or 'pending'} {url}")
if status != "completed" or conclusion != "success":
    raise SystemExit(f"[Ithute] Refusing deployment: {label} is not green for current main {sha}")
PY
}

check_workflow ci.yml "Ithute Standalone CI"
check_workflow production-safety-ci.yml "Production Safety CI"
check_workflow release-images.yml "Ithute Release Images"

echo "[Ithute] Current production: ${current:-unknown}"
echo "[Ithute] Deploying approved current main: $MAIN_SHA"

if [ "$(id -u)" -eq 0 ]; then
  exec "$REMOTE_HELPER" "$MAIN_SHA"
else
  exec sudo "$REMOTE_HELPER" "$MAIN_SHA"
fi
