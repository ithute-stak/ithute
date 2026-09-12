#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${ITHUTE_APP_DIR:-/home/administrator/ithute}"
REPO_URL="${ITHUTE_REPO_URL:-https://github.com/ithute-stak/ithute.git}"
ENV_FILE="$APP_DIR/.env.production"
BOOTSTRAP_MARKER="$APP_DIR/.ithute-bootstrapped"
OWNER_EMAIL="thekoetlisi@ithute.co.ls"

for command in docker git openssl curl; do
  command -v "$command" >/dev/null 2>&1 || { echo "Required command not found: $command" >&2; exit 2; }
done
docker compose version >/dev/null

if [ -e /home/administrator/ithute-edge ] || [ -e /home/administrator/mailbox-dns ]; then
  echo "Old deployment directories still exist." >&2
  echo "Complete the explicit one-time VPS cleanup before running this bootstrap." >&2
  exit 2
fi

if [ ! -d "$APP_DIR/.git" ]; then
  if [ -e "$APP_DIR" ] && [ -n "$(ls -A "$APP_DIR" 2>/dev/null || true)" ]; then
    echo "$APP_DIR exists but is not a clean Git checkout; refusing to overwrite it." >&2
    exit 2
  fi
  rmdir "$APP_DIR" 2>/dev/null || true
  git clone --branch main --single-branch "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch --prune origin main
  git -C "$APP_DIR" checkout main
  git -C "$APP_DIR" reset --hard origin/main
fi

cd "$APP_DIR"

if [ -f "$ENV_FILE" ]; then
  echo "$ENV_FILE already exists; refusing to overwrite production secrets." >&2
  echo "Use scripts/deploy-production.sh for normal updates." >&2
  exit 2
fi

printf 'System owner: %s\n' "$OWNER_EMAIL"
read -r -s -p 'Enter the system-owner password: ' OWNER_PASSWORD
printf '\n'
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
mkdir -p "$APP_DIR/secrets/ithute-auth" "$APP_DIR/secrets/ithute-push"
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
unset OWNER_PASSWORD

bash "$APP_DIR/scripts/deploy-production.sh"
touch "$BOOTSTRAP_MARKER"
chmod 600 "$BOOTSTRAP_MARKER"

printf '\nFresh Ithute application deployment completed.\n'
printf 'Owner login: %s\n' "$OWNER_EMAIL"
printf 'Auth portal: https://auth.ithute.co.ls/account/login\n'
printf '\nAttempting independent mail bootstrap next...\n'
if bash "$APP_DIR/scripts/bootstrap-mail.sh"; then
  printf 'Mail bootstrap completed.\n'
else
  status=$?
  if [ "$status" -eq 3 ]; then
    printf '\nMail is staged but public DNS is not ready yet.\n'
    printf 'Apply the records shown by the mail bootstrap, then rerun: bash scripts/bootstrap-mail.sh\n'
  else
    exit "$status"
  fi
fi
