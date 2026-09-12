#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute-platform}"
MAIL_DIR="${ITHUTE_MAIL_DIR:-/home/administrator/ithute-platform-mail}"
ENV_FILE="$APP_DIR/.env.production"
BOOTSTRAP_MARKER="$APP_DIR/.ithute-bootstrapped"
DEPLOY_SCRIPT="${ITHUTE_DEPLOY_SCRIPT:-/tmp/ithute-deploy-production.sh}"
IMAGE_TAG="${ITHUTE_IMAGE_TAG:-}"
OWNER_EMAIL="thekoetlisi@ithute.co.ls"

for command in docker openssl curl; do
  command -v "$command" >/dev/null 2>&1 || { echo "Required command not found: $command" >&2; exit 2; }
done
docker compose version >/dev/null

# The VPS stores runtime configuration, secrets and persistent Docker data only.
# Application source is built into immutable images by GitHub Actions.
if [ "$APP_DIR" = "/" ] || [ "$APP_DIR" = "/home" ] || [ "$APP_DIR" = "/home/administrator" ]; then
  echo "Unsafe Ithute application directory: $APP_DIR" >&2
  exit 2
fi
if [ "$MAIL_DIR" = "/" ] || [ "$MAIL_DIR" = "/home" ] || [ "$MAIL_DIR" = "/home/administrator" ]; then
  echo "Unsafe Ithute mail directory: $MAIL_DIR" >&2
  exit 2
fi
if [ "$APP_DIR" = "$MAIL_DIR" ]; then
  echo "Application and mail directories must be separate." >&2
  exit 2
fi
case "$IMAGE_TAG" in
  *[!0-9a-f]*|'') echo "ITHUTE_IMAGE_TAG must be a lowercase Git commit SHA." >&2; exit 2 ;;
esac
if [ "${#IMAGE_TAG}" -ne 40 ]; then
  echo "ITHUTE_IMAGE_TAG must be a full 40-character Git commit SHA." >&2
  exit 2
fi

test -x "$DEPLOY_SCRIPT" || { echo "Missing executable deployment script: $DEPLOY_SCRIPT" >&2; exit 2; }
mkdir -p "$APP_DIR/infrastructure/caddy" "$APP_DIR/secrets/ithute-auth" "$APP_DIR/secrets/ithute-push"
test -f "$APP_DIR/compose.production.yml" || { echo "Missing runtime compose file" >&2; exit 2; }
test -f "$APP_DIR/infrastructure/caddy/Caddyfile" || { echo "Missing runtime Caddyfile" >&2; exit 2; }

if [ -f "$ENV_FILE" ]; then
  echo "$ENV_FILE already exists; refusing to overwrite production secrets." >&2
  echo "Use the normal image deployment workflow for updates." >&2
  exit 2
fi

if [ -n "${ITHUTE_SYSTEM_OWNER_PASSWORD_B64:-}" ]; then
  OWNER_PASSWORD="$(printf '%s' "$ITHUTE_SYSTEM_OWNER_PASSWORD_B64" | base64 -d)"
elif [ -n "${ITHUTE_SYSTEM_OWNER_PASSWORD:-}" ]; then
  OWNER_PASSWORD="$ITHUTE_SYSTEM_OWNER_PASSWORD"
else
  printf 'System owner: %s\n' "$OWNER_EMAIL"
  read -r -s -p 'Enter the system-owner password: ' OWNER_PASSWORD
  printf '\n'
fi

[ ${#OWNER_PASSWORD} -ge 12 ] || { echo "Owner password must contain at least 12 characters." >&2; exit 2; }
case "$OWNER_PASSWORD" in
  *$'\n'*|*$'\r'*) echo "Owner password cannot contain a newline." >&2; exit 2 ;;
  *"'"*) echo "Owner password cannot contain a single quote in this bootstrap path." >&2; exit 2 ;;
esac

random_hex() { openssl rand -hex "$1"; }
fernet_key() { openssl rand 32 | base64 | tr '+/' '-_' | tr -d '\n'; }

AUTH_DB_PASSWORD="$(random_hex 32)"
PUSH_DB_PASSWORD="$(random_hex 32)"
REALTIME_DB_PASSWORD="$(random_hex 32)"
AUTH_TOTP_KEY="$(fernet_key)"
PUSH_ENDPOINT_KEY="$(fernet_key)"
REALTIME_SECRET="$(random_hex 32)"

umask 077
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$APP_DIR/secrets/ithute-auth/jwt-private.pem"
openssl pkey -in "$APP_DIR/secrets/ithute-auth/jwt-private.pem" -pubout -out "$APP_DIR/secrets/ithute-auth/jwt-public.pem"
chmod 600 "$APP_DIR/secrets/ithute-auth/jwt-private.pem" "$APP_DIR/secrets/ithute-auth/jwt-public.pem"

cat > "$ENV_FILE" <<EOF
ITHUTE_AUTH_ISSUER=https://auth.ithute.co.ls
ITHUTE_AUTH_ACCOUNT_BASE_URL=https://auth.ithute.co.ls
ITHUTE_REALTIME_PUBLIC_URL=https://realtime.ithute.co.ls
ITHUTE_AUTH_DB_NAME=ithute_auth
ITHUTE_AUTH_DB_USER=ithute_auth
ITHUTE_AUTH_DB_PASSWORD=$AUTH_DB_PASSWORD
ITHUTE_PUSH_DB_NAME=ithute_push
ITHUTE_PUSH_DB_USER=ithute_push
ITHUTE_PUSH_DB_PASSWORD=$PUSH_DB_PASSWORD
ITHUTE_REALTIME_DB_NAME=ithute_realtime
ITHUTE_REALTIME_DB_USER=ithute_realtime
ITHUTE_REALTIME_DB_PASSWORD=$REALTIME_DB_PASSWORD
ITHUTE_AUTH_TOTP_ENCRYPTION_KEY=$AUTH_TOTP_KEY
ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY=$PUSH_ENDPOINT_KEY
ITHUTE_SERVICE_REALTIME_SECRET=$REALTIME_SECRET
ITHUTE_SYSTEM_OWNER_EMAIL=$OWNER_EMAIL
ITHUTE_SYSTEM_OWNER_PASSWORD='$OWNER_PASSWORD'
ITHUTE_AUTH_FIRST_PARTY_CLIENTS=ithute-realtime:!thute Realtime
ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON={"ithute-realtime":"$REALTIME_SECRET"}
ITHUTE_AUTH_REDIRECT_URIS_JSON={}
ITHUTE_AUTH_CORS_ORIGINS=https://ithute.co.ls,https://auth.ithute.co.ls
ITHUTE_PUSH_ALLOWED_USER_CLIENTS=
ITHUTE_PUSH_ALLOWED_SERVICE_CLIENTS=ithute-realtime
ITHUTE_PUSH_DELEGATED_SERVICE_CLIENTS=ithute-realtime
ITHUTE_PUSH_ALLOWED_ADMIN_CLIENTS=
ITHUTE_REALTIME_ALLOWED_USER_CLIENTS=
ITHUTE_REALTIME_ALLOWED_SERVICE_CLIENTS=
ITHUTE_REALTIME_PUSH_ENABLED=true
ITHUTE_PUSH_REQUIRED_PROVIDERS=
ITHUTE_PUSH_FCM_PROJECT_ID=
ITHUTE_PUSH_FCM_ANDROID_CHANNEL_ID=ithute_default
ITHUTE_AUTH_SMTP_HOST=
ITHUTE_AUTH_SMTP_PORT=587
ITHUTE_AUTH_SMTP_USERNAME=
ITHUTE_AUTH_SMTP_PASSWORD=
ITHUTE_AUTH_SMTP_FROM=
ITHUTE_AUTH_SMTP_STARTTLS=true
EOF
chmod 600 "$ENV_FILE"
unset OWNER_PASSWORD ITHUTE_SYSTEM_OWNER_PASSWORD ITHUTE_SYSTEM_OWNER_PASSWORD_B64

ITHUTE_APP_DIR="$APP_DIR" ITHUTE_IMAGE_TAG="$IMAGE_TAG" bash "$DEPLOY_SCRIPT"
touch "$BOOTSTRAP_MARKER"
chmod 600 "$BOOTSTRAP_MARKER"

printf '\nFresh Ithute runtime bootstrap completed.\n'
printf 'Application runtime directory: %s\n' "$APP_DIR"
printf 'Image tag: %s\n' "$IMAGE_TAG"
printf 'Owner login: %s\n' "$OWNER_EMAIL"
printf 'Auth portal: https://auth.ithute.co.ls/account/login\n'
printf 'Application source code was not cloned to the VPS.\n'
