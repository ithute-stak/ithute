#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
REPO="ithute-stak/ithute"
API="https://api.github.com/repos/$REPO"
LOCAL_HELPER="$APP_DIR/scripts/deploy-production-manual.sh"
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
  local attempt
  local max_attempts="${ITHUTE_GATE_DISCOVERY_ATTEMPTS:-12}"
  local sleep_seconds="${ITHUTE_GATE_DISCOVERY_DELAY_SECONDS:-5}"

  for attempt in $(seq 1 "$max_attempts"); do
    curl --retry 5 --retry-delay 2 --retry-all-errors -fsSL \
      "$API/actions/workflows/$workflow/runs?branch=main&per_page=100" \
      -o "$output"

    if python3 - "$MAIN_SHA" "$output" "$label" "$attempt" "$max_attempts" <<'PY'
import json
import sys

sha, path, label, attempt, max_attempts = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    runs = json.load(handle).get("workflow_runs", [])
matching = [run for run in runs if run.get("head_sha") == sha and run.get("head_branch") == "main"]
matching.sort(key=lambda run: run.get("created_at") or "", reverse=True)
if not matching:
    print(f"[Ithute] {label}: exact-SHA run not indexed yet ({attempt}/{max_attempts})")
    raise SystemExit(10)

actionable = [run for run in matching if run.get("conclusion") != "skipped"]
if not actionable:
    print(f"[Ithute] {label}: exact-SHA run exists but is not actionable yet ({attempt}/{max_attempts})")
    raise SystemExit(10)

run = actionable[0]
status = run.get("status")
conclusion = run.get("conclusion")
url = run.get("html_url") or ""
print(f"[Ithute] {label}: status={status} conclusion={conclusion or 'pending'} {url}")
if status == "completed" and conclusion == "success":
    raise SystemExit(0)
if status == "completed":
    raise SystemExit(20)
raise SystemExit(10)
PY
    then
      return 0
    else
      rc=$?
    fi

    if [ "$rc" -eq 20 ]; then
      echo "[Ithute] Refusing deployment: $label is not green for current main $MAIN_SHA" >&2
      return 1
    fi
    if [ "$attempt" -lt "$max_attempts" ]; then
      sleep "$sleep_seconds"
      continue
    fi
    echo "[Ithute] $label did not become visible and green for current main $MAIN_SHA after $max_attempts checks" >&2
    return 1
  done
}

check_workflow ci.yml "Ithute Standalone CI"
check_workflow production-safety-ci.yml "Production Safety CI"
check_workflow release-images.yml "Ithute Release Images"

echo "[Ithute] Current production: ${current:-unknown}"
echo "[Ithute] Deploying approved current main: $MAIN_SHA"

EXACT_HELPER="$tmpdir/deploy-production-manual.sh"
echo "[Ithute] Fetching exact deployment helper deploy-production-manual.sh@$MAIN_SHA"
curl --retry 5 --retry-delay 2 --retry-all-errors -fsSL   "$REPO_RAW/$MAIN_SHA/scripts/deploy-production-manual.sh"   -o "$EXACT_HELPER"
test -s "$EXACT_HELPER" || { echo "Approved deployment helper is empty." >&2; exit 1; }
bash -n "$EXACT_HELPER"
for required_image in ithute-web ithute-app-api ithute-go-worker ithute-java-worker ithute-auth ithute-push ithute-realtime; do
  grep -Fq "$required_image" "$EXACT_HELPER" || {
    echo "Refusing deployment: exact helper for $MAIN_SHA does not include required image $required_image." >&2
    exit 1
  }
done
chmod 700 "$EXACT_HELPER"

# Keep the installed helper current for direct/manual use as well, but execute
# the exact approved copy from the temporary release directory.
install -m 700 "$EXACT_HELPER" "$LOCAL_HELPER"

if [ "$(id -u)" -eq 0 ]; then
  exec "$EXACT_HELPER" "$MAIN_SHA"
else
  exec sudo "$EXACT_HELPER" "$MAIN_SHA"
fi
