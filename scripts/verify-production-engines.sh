#!/usr/bin/env bash
# Read-only verification of the deployed multi-engine runtime. Run on the Ithute host.
set -euo pipefail

COMPOSE_FILE="${ITHUTE_COMPOSE_FILE:-compose.production.yml}"
ENV_FILE="${ITHUTE_ENV_FILE:-.env.production}"
if [[ ! -f "$COMPOSE_FILE" || ! -f "$ENV_FILE" ]]; then
  echo "ERROR: production Compose or environment file is unavailable." >&2
  exit 2
fi
command -v docker >/dev/null || { echo "ERROR: docker is unavailable." >&2; exit 2; }

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T ithute-app-api python - <<'PY'
import json
import sys

from app.services.engine_runtime import engine_status

status = engine_status()
engines = status.get("engines", {})
results = {}
for name in ("rust", "cpp", "go", "java"):
    item = engines.get(name) or {}
    results[name] = {
        "available": item.get("available") is True,
        "mode": item.get("mode"),
        "capabilities": item.get("capabilities", []),
    }
print(json.dumps({"python_authoritative": status.get("brain", {}).get("authoritative") is True, "engines": results}, indent=2))
if status.get("brain", {}).get("authoritative") is not True or not all(item["available"] for item in results.values()):
    print("FAIL: one or more configured runtime engines are unavailable.", file=sys.stderr)
    sys.exit(1)
print("PASS: all four specialist engines respond to the Python runtime.")
PY
