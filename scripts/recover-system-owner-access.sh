#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
PASSWORD_FILE="${ITHUTE_OWNER_PASSWORD_FILE:-/tmp/ithute-owner-password.b64}"
ENV_FILE="$APP_DIR/.env.production"
IMAGE_ENV="$APP_DIR/.image.env"

if [ "$APP_DIR" = "/" ] || [ "$APP_DIR" = "/home" ] || [ "$APP_DIR" = "/home/administrator" ]; then
  echo "Unsafe Ithute application directory: $APP_DIR" >&2
  exit 2
fi

test -f "$ENV_FILE" || { echo "Missing production environment: $ENV_FILE" >&2; exit 2; }
test -f "$IMAGE_ENV" || { echo "Missing image environment: $IMAGE_ENV" >&2; exit 2; }
test -f "$APP_DIR/compose.production.yml" || { echo "Missing production Compose file" >&2; exit 2; }
test -s "$PASSWORD_FILE" || { echo "Missing protected owner password payload" >&2; exit 2; }

OWNER_PASSWORD="$(base64 -d < "$PASSWORD_FILE")"
trap 'unset OWNER_PASSWORD; rm -f "$PASSWORD_FILE"' EXIT

[ "${#OWNER_PASSWORD}" -ge 12 ] || { echo "Protected owner password must contain at least 12 characters" >&2; exit 2; }
case "$OWNER_PASSWORD" in
  *$'\n'*|*$'\r'*) echo "Protected owner password cannot contain a newline" >&2; exit 2 ;;
  *"'"*) echo "Protected owner password contains a quote unsupported by the current env-file format" >&2; exit 2 ;;
esac

# Make the protected GitHub production secret authoritative for the already-
# bootstrapped runtime without changing any database, volume, or other product.
tmp_env="$(mktemp "$APP_DIR/.env.production.recovery.XXXXXX")"
awk '!/^ITHUTE_SYSTEM_OWNER_PASSWORD=/' "$ENV_FILE" > "$tmp_env"
printf "ITHUTE_SYSTEM_OWNER_PASSWORD='%s'\n" "$OWNER_PASSWORD" >> "$tmp_env"
chmod 600 "$tmp_env"
mv "$tmp_env" "$ENV_FILE"

cd "$APP_DIR"
compose() {
  docker compose \
    --env-file .env.production \
    --env-file .image.env \
    -p ithute \
    -f compose.production.yml \
    "$@"
}

# Recreate only Auth so the process receives the refreshed protected secret.
# Persistent PostgreSQL data and every other Ithute/product container remain in place.
compose up -d --no-build --no-deps --force-recreate ithute-auth

healthy=false
for _ in $(seq 1 30); do
  if compose exec -T ithute-auth curl -fsS http://127.0.0.1:8080/healthz 2>/dev/null | grep -q ithute-auth; then
    healthy=true
    break
  fi
  sleep 2
done
[ "$healthy" = true ] || { echo "Ithute Auth did not become healthy after owner recovery" >&2; exit 1; }

# Startup synchronizes the configured system-owner password. This privileged,
# explicit recovery additionally clears only that owner's login lock state.
compose exec -T ithute-auth python - <<'PY'
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from app.security import normalize_email

settings = get_settings()
email = normalize_email(settings.system_owner_email)
if not email:
    raise SystemExit("system owner email is not configured")

with SessionLocal() as db:
    owner = db.scalar(select(User).where(User.email == email))
    if owner is None:
        raise SystemExit("configured system owner was not provisioned")

    owner.is_active = True
    owner.is_platform_admin = True
    owner.email_verified = True
    owner.failed_login_attempts = 0
    owner.locked_until = None
    db.commit()
    db.refresh(owner)

    print(f"owner_email={owner.email}")
    print(f"owner_active={'true' if owner.is_active else 'false'}")
    print(f"owner_admin={'true' if owner.is_platform_admin else 'false'}")
    print(f"mfa_enabled={'true' if owner.totp_enabled else 'false'}")
PY

printf 'System-owner access recovery completed without recreating persistent data.\n'
