#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_SELECTOR="${1:-latest}"
APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
REGISTRY="${ITHUTE_GHCR_REGISTRY:-ghcr.io/ithute-stak}"
MIN_FREE_KB="${ITHUTE_MIN_FREE_KB:-15728640}"
REPO_RAW="https://raw.githubusercontent.com/ithute-stak/ithute"
REPO_GIT="https://github.com/ithute-stak/ithute.git"
IMAGES=(ithute-web ithute-app-api ithute-auth ithute-push ithute-realtime)

if [ "$RELEASE_SELECTOR" = "latest" ]; then
  echo "[Ithute] Resolving latest main release"
  RELEASE_SHA="$(git ls-remote "$REPO_GIT" refs/heads/main | awk '{print $1}')"
else
  RELEASE_SHA="$RELEASE_SELECTOR"
fi

if [[ ! "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: $0 [latest|40-character-tested-release-sha]" >&2
  exit 2
fi

if [ "$APP_DIR" != "/home/administrator/ithute-platform" ]; then
  echo "Refusing to operate outside /home/administrator/ithute-platform." >&2
  exit 2
fi

cd "$APP_DIR"
test -f .ithute-bootstrapped || { echo "Missing $APP_DIR/.ithute-bootstrapped" >&2; exit 1; }
test -f .env.production || { echo "Missing $APP_DIR/.env.production" >&2; exit 1; }
test -d secrets || { echo "Missing $APP_DIR/secrets" >&2; exit 1; }
docker info >/dev/null

valid_tag() {
  [[ "${1:-}" =~ ^[0-9a-f]{40}$ ]]
}

read_tag() {
  local file="$1"
  [ -f "$file" ] || return 0
  sed -n 's/^ITHUTE_IMAGE_TAG=//p' "$file" | tail -n1
}

current="$(read_tag "$APP_DIR/.image.env")"
last_good="$(read_tag "$APP_DIR/.last-known-good.env")"

if [ "$current" = "$RELEASE_SHA" ]; then
  echo "[Ithute] Production is already running release $RELEASE_SHA; nothing to do."
  exit 0
fi

rollback=""
if valid_tag "$current"; then
  rollback="$current"
elif valid_tag "$last_good"; then
  rollback="$last_good"
else
  echo "No valid current or last-known-good Ithute release is available for rollback." >&2
  exit 1
fi

echo "[Ithute] Candidate: $RELEASE_SHA"
echo "[Ithute] Rollback:  $rollback"
echo "[Ithute] Checking targeted storage headroom"

df -h / /tmp || true
docker system df || true

running_images="$(docker ps --format '{{.Image}}' | sort -u)"
for repo in "${IMAGES[@]}"; do
  docker image ls "$repo" --format '{{.Repository}}:{{.Tag}}' | sort -u | while IFS= read -r image; do
    [ -n "$image" ] || continue
    if printf '%s\n' "$running_images" | grep -Fxq "$image"; then
      echo "[Ithute] Keeping running image $image"
    elif [ "$image" = "$repo:$rollback" ] || [ "$image" = "$repo:$RELEASE_SHA" ]; then
      echo "[Ithute] Keeping protected image $image"
    else
      echo "[Ithute] Removing stale Ithute image $image"
      docker image rm "$image" >/dev/null 2>&1 || true
    fi
  done
done
docker image prune -f >/dev/null 2>&1 || true

available_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
available_inodes="$(df -Pi / | awk 'NR==2 {print $4}')"
if [ "${available_kb:-0}" -lt "$MIN_FREE_KB" ]; then
  echo "Refusing deployment: less than 15 GiB free after safe Ithute-only cleanup." >&2
  exit 1
fi
if [ "${available_inodes:-0}" -lt 100000 ]; then
  echo "Refusing deployment: fewer than 100,000 free inodes." >&2
  exit 1
fi

pull_as_local() {
  local repo="$1"
  local tag="$2"
  local local_ref="$repo:$tag"
  local remote_ref="$REGISTRY/$repo:$tag"

  if docker image inspect "$local_ref" >/dev/null 2>&1; then
    echo "[Ithute] Already available: $local_ref"
    return 0
  fi

  echo "[Ithute] Pulling $remote_ref"
  if ! docker pull "$remote_ref"; then
    echo "Unable to pull $remote_ref. Authenticate first with: sudo docker login ghcr.io" >&2
    return 1
  fi
  docker tag "$remote_ref" "$local_ref"
  docker image rm "$remote_ref" >/dev/null 2>&1 || true
  docker image inspect "$local_ref" >/dev/null
}

for repo in "${IMAGES[@]}"; do
  pull_as_local "$repo" "$RELEASE_SHA"
done
for repo in "${IMAGES[@]}"; do
  pull_as_local "$repo" "$rollback"
done

tmpdir="$(mktemp -d /tmp/ithute-release.XXXXXX)"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

mkdir -p "$tmpdir/infrastructure/caddy" "$tmpdir/infrastructure/dns/zones" "$tmpdir/infrastructure/wireguard-edge" "$tmpdir/scripts"
fetch_runtime() {
  local path="$1"
  local destination="$2"
  echo "[Ithute] Fetching exact runtime file $path@$RELEASE_SHA"
  curl --retry 5 --retry-delay 2 --retry-all-errors -fsSL \
    "$REPO_RAW/$RELEASE_SHA/$path" \
    -o "$destination"
  test -s "$destination"
}

fetch_runtime compose.production.yml "$tmpdir/compose.production.yml"
fetch_runtime infrastructure/caddy/Caddyfile "$tmpdir/infrastructure/caddy/Caddyfile"
fetch_runtime infrastructure/dns/zones/db.ithute.co.ls "$tmpdir/infrastructure/dns/zones/db.ithute.co.ls"
fetch_runtime scripts/deploy-production.sh "$tmpdir/scripts/deploy-production.sh"
fetch_runtime infrastructure/wireguard-edge/bootstrap.sh "$tmpdir/infrastructure/wireguard-edge/bootstrap.sh"
fetch_runtime infrastructure/wireguard-edge/reconcile.sh "$tmpdir/infrastructure/wireguard-edge/reconcile.sh"
fetch_runtime infrastructure/wireguard-edge/ithute-wireguard-edge-reconciler.service "$tmpdir/infrastructure/wireguard-edge/ithute-wireguard-edge-reconciler.service"
fetch_runtime infrastructure/wireguard-edge/ithute-wireguard-edge-reconciler.timer "$tmpdir/infrastructure/wireguard-edge/ithute-wireguard-edge-reconciler.timer"
bash -n "$tmpdir/scripts/deploy-production.sh"
bash -n "$tmpdir/infrastructure/wireguard-edge/bootstrap.sh"
bash -n "$tmpdir/infrastructure/wireguard-edge/reconcile.sh"

if [ ! -s "$APP_DIR/.last-known-good-runtime.tgz" ] && valid_tag "$current"; then
  echo "[Ithute] Preserving current runtime for rollback"
  tar -czf "$APP_DIR/.last-known-good-runtime.tgz" -C "$APP_DIR" \
    compose.production.yml \
    infrastructure/caddy/Caddyfile \
    infrastructure/dns/zones/db.ithute.co.ls \
    infrastructure/wireguard-edge
  chmod 600 "$APP_DIR/.last-known-good-runtime.tgz"
fi

mkdir -p "$APP_DIR/infrastructure/caddy" "$APP_DIR/infrastructure/dns/zones" "$APP_DIR/infrastructure/wireguard-edge"
cp "$tmpdir/compose.production.yml" "$APP_DIR/compose.production.yml"
cp "$tmpdir/infrastructure/caddy/Caddyfile" "$APP_DIR/infrastructure/caddy/Caddyfile"
cp "$tmpdir/infrastructure/dns/zones/db.ithute.co.ls" "$APP_DIR/infrastructure/dns/zones/db.ithute.co.ls"
cp "$tmpdir/infrastructure/wireguard-edge/"* "$APP_DIR/infrastructure/wireguard-edge/"
chmod 700 "$APP_DIR/infrastructure/wireguard-edge/bootstrap.sh" "$APP_DIR/infrastructure/wireguard-edge/reconcile.sh"

echo "[Ithute] Starting candidate through the existing rollback-safe deployment engine"
ITHUTE_APP_DIR="$APP_DIR" \
ITHUTE_IMAGE_TAG="$RELEASE_SHA" \
ITHUTE_FALLBACK_IMAGE_TAG="$rollback" \
ITHUTE_REQUIRE_PUBLIC_HEALTH=1 \
  bash "$tmpdir/scripts/deploy-production.sh"

grep -Fxq "ITHUTE_IMAGE_TAG=$RELEASE_SHA" "$APP_DIR/.image.env"
grep -Fxq "ITHUTE_IMAGE_TAG=$RELEASE_SHA" "$APP_DIR/.last-known-good.env"
test -s "$APP_DIR/.last-known-good-runtime.tgz"

compose=(docker compose --env-file "$APP_DIR/.env.production" --env-file "$APP_DIR/.image.env" -p ithute -f "$APP_DIR/compose.production.yml")
for service_repo in \
  "ithute-web:ithute-web" \
  "ithute-app-api:ithute-app-api" \
  "ithute-auth:ithute-auth" \
  "ithute-push:ithute-push" \
  "ithute-realtime:ithute-realtime"; do
  service="${service_repo%%:*}"
  repo="${service_repo##*:}"
  container_id="$("${compose[@]}" ps -q "$service")"
  test -n "$container_id" || { echo "Missing running container for $service" >&2; exit 1; }
  actual="$(docker inspect --format '{{.Config.Image}}' "$container_id")"
  test "$actual" = "$repo:$RELEASE_SHA" || {
    echo "$service is running $actual instead of $repo:$RELEASE_SHA" >&2
    exit 1
  }
done

printf '\n[Ithute] Production is healthy on release %s\n' "$RELEASE_SHA"
printf '[Ithute] Previous release retained for rollback: %s\n' "$rollback"
