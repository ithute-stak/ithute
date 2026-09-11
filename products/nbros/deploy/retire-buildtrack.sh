#!/usr/bin/env sh
set -eu

: "${PLATFORM_ROOT:?PLATFORM_ROOT is required}"

lower_contains_buildtrack() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | grep -q 'buildtrack'
}

echo "Retiring legacy BuildTrack production resources."

# Remove legacy BuildTrack containers first so their volumes and networks are
# no longer in use. Match both container names and Compose service labels.
container_ids="$(
  {
    docker ps -aq --filter 'name=buildtrack' 2>/dev/null || true
    for service in buildtrack-backend buildtrack-frontend buildtrack-db buildtrack-redis; do
      docker ps -aq --filter "label=com.docker.compose.service=${service}" 2>/dev/null || true
    done
  } | awk 'NF && !seen[$0]++'
)"
if [ -n "$container_ids" ]; then
  printf '%s\n' "$container_ids" | xargs -r docker rm -f
fi

# Delete every Docker volume and network whose name belongs to BuildTrack.
# This intentionally removes the retired product database and Redis data.
for volume in $(docker volume ls --format '{{.Name}}' | grep -Ei 'buildtrack' || true); do
  docker volume rm -f "$volume"
done
for network in $(docker network ls --format '{{.Name}}' | grep -Ei 'buildtrack' || true); do
  docker network rm "$network" >/dev/null 2>&1 || true
done

# Remove locally cached BuildTrack images after the containers are gone.
image_ids="$(docker image ls --format '{{.Repository}} {{.ID}}' | awk 'tolower($1) ~ /buildtrack/ {print $2}' | sort -u)"
if [ -n "$image_ids" ]; then
  printf '%s\n' "$image_ids" | xargs -r docker image rm -f >/dev/null 2>&1 || true
fi

# Remove stale runtime files/directories left by the retired product.
find "$PLATFORM_ROOT" -maxdepth 2 \( -type f -o -type d \) -iname '*buildtrack*' -print 2>/dev/null \
  | sort -r \
  | while IFS= read -r path; do
      [ "$path" = "$PLATFORM_ROOT" ] && continue
      rm -rf "$path"
    done

# Remove BuildTrack-only environment keys and central client registrations,
# while preserving nbro.ithute.co.ls because that hostname now belongs to NBros.
CENTRAL_ENV="$PLATFORM_ROOT/.env"
if [ -s "$CENTRAL_ENV" ]; then
  python3 - "$CENTRAL_ENV" <<'PY'
from pathlib import Path
import json
import re
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

json_keys = {
    "ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON",
    "ITHUTE_AUTH_REDIRECT_URIS_JSON",
}
list_keys = {
    "ITHUTE_AUTH_FIRST_PARTY_CLIENTS",
    "ITHUTE_PUSH_ALLOWED_USER_CLIENTS",
    "ITHUTE_PUSH_ALLOWED_SERVICE_CLIENTS",
    "ITHUTE_PUSH_ALLOWED_ADMIN_CLIENTS",
    "ITHUTE_REALTIME_ALLOWED_USER_CLIENTS",
    "ITHUTE_REALTIME_ALLOWED_SERVICE_CLIENTS",
    "ITHUTE_REALTIME_DISABLED_CLIENTS",
}

def is_buildtrack_client(value: str) -> bool:
    client = value.split(":", 1)[0].strip().lower()
    return client.startswith("buildtrack")

out: list[str] = []
for line in lines:
    if not line or line.lstrip().startswith("#") or "=" not in line:
        out.append(line)
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if "BUILDTRACK" in key.upper():
        continue
    if key in json_keys:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            out.append(line)
            continue
        if isinstance(parsed, dict):
            parsed = {k: v for k, v in parsed.items() if not str(k).lower().startswith("buildtrack")}
            value = json.dumps(parsed, separators=(",", ":"))
        out.append(f"{key}={value}")
        continue
    if key in list_keys:
        items = [item.strip() for item in value.split(",") if item.strip()]
        items = [item for item in items if not is_buildtrack_client(item)]
        out.append(f"{key}={','.join(items)}")
        continue
    out.append(line)

path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  chmod 600 "$CENTRAL_ENV"
fi

# Strong post-condition: no BuildTrack runtime objects may remain locally.
if docker ps -a --format '{{.Names}}' | grep -Eqi 'buildtrack'; then
  echo "BuildTrack container still exists after retirement." >&2
  docker ps -a --format '{{.Names}}\t{{.Image}}' | grep -Ei 'buildtrack' >&2 || true
  exit 1
fi
if docker volume ls --format '{{.Name}}' | grep -Eqi 'buildtrack'; then
  echo "BuildTrack volume still exists after retirement." >&2
  docker volume ls --format '{{.Name}}' | grep -Ei 'buildtrack' >&2 || true
  exit 1
fi
if docker network ls --format '{{.Name}}' | grep -Eqi 'buildtrack'; then
  echo "BuildTrack network still exists after retirement." >&2
  docker network ls --format '{{.Name}}' | grep -Ei 'buildtrack' >&2 || true
  exit 1
fi
if docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -Eqi 'buildtrack'; then
  echo "BuildTrack image still exists after retirement." >&2
  docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -Ei 'buildtrack' >&2 || true
  exit 1
fi

echo "Legacy BuildTrack production runtime has been fully retired."
