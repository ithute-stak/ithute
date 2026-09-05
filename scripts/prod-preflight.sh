#!/usr/bin/env sh
set -eu

[ -f .env ] || { echo "Missing .env"; exit 1; }
. scripts/load-dotenv.sh
load_dotenv .env

fail=0

require() {
  name="$1"
  eval "value=\${$name:-}"
  [ -n "$value" ] || { echo "ERROR: $name is required for production"; fail=1; }
}

reject_placeholder() {
  name="$1"
  eval "value=\${$name:-}"
  case "$value" in
    *replace-with*|*replace-this*|*development*|*ChangeMe*|*changeme*|*example-secret*|"")
      echo "ERROR: $name is missing or still uses a placeholder value"
      fail=1
      ;;
  esac
}

[ "${ENVIRONMENT:-}" = "production" ] || { echo "ERROR: ENVIRONMENT must be production"; fail=1; }

case "${PLATFORM_MODE:-bootstrap}" in
  bootstrap|domain) ;;
  *) echo "ERROR: PLATFORM_MODE must be bootstrap or domain"; fail=1 ;;
esac

for name in BOOTSTRAP_PUBLIC_IP MAIL_PUBLIC_IP RESTIC_REPOSITORY BOOTSTRAP_ADMIN_EMAIL; do
  require "$name"
done

for name in SECRET_KEY DKIM_ENCRYPTION_KEY BILLING_WEBHOOK_SECRET POSTGRES_PASSWORD POWERDNS_API_KEY POWERDNS_DB_PASSWORD MAIL_OPS_TOKEN RECOVERY_OPS_TOKEN MAIL_NODE_TOKEN RESTIC_PASSWORD RESTORE_DB_PASSWORD GRAFANA_ADMIN_PASSWORD BOOTSTRAP_ADMIN_PASSWORD ITHUTE_AUTH_DB_PASSWORD ITHUTE_PUSH_DB_PASSWORD ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY; do
  reject_placeholder "$name"
done

if [ "${SECRET_KEY:-}" = "${DKIM_ENCRYPTION_KEY:-}" ] && [ -n "${SECRET_KEY:-}" ]; then
  echo "ERROR: DKIM_ENCRYPTION_KEY must be distinct from SECRET_KEY"
  fail=1
fi

if [ "${ITHUTE_AUTH_DB_PASSWORD:-}" = "${ITHUTE_PUSH_DB_PASSWORD:-}" ]; then
  echo "ERROR: !thute Auth and !thute Push must use different database passwords"
  fail=1
fi

case "${ITHUTE_AUTH_ISSUER:-}" in
  https://auth.ithute.co.ls) ;;
  *) echo "ERROR: ITHUTE_AUTH_ISSUER must be https://auth.ithute.co.ls in production"; fail=1 ;;
esac

# Fernet keys are URL-safe base64-encoded 32-byte keys (44 characters with
# padding). The service validates cryptographically again on startup.
case "${ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY:-}" in
  ???????????????????????????????????????????=) ;;
  *) echo "ERROR: ITHUTE_PUSH_ENDPOINT_ENCRYPTION_KEY does not look like a Fernet key"; fail=1 ;;
esac

for key_file in platform-secrets/ithute-auth/jwt-private.pem platform-secrets/ithute-auth/jwt-public.pem; do
  [ -s "$key_file" ] || { echo "ERROR: missing central Auth key file $key_file"; fail=1; }
done

case "${NEXT_PUBLIC_API_URL:-}" in
  https://*|/api/*) ;;
  *) echo "ERROR: NEXT_PUBLIC_API_URL must use https:// or a same-origin /api/ path in production"; fail=1 ;;
esac

if [ "${PLATFORM_MODE:-bootstrap}" = "bootstrap" ]; then
  case "${FRONTEND_URL:-}" in
    https://*)
      [ "${COOKIE_SECURE:-}" = "true" ] || {
        echo "ERROR: bootstrap mode served over HTTPS requires COOKIE_SECURE=true"
        fail=1
      }
      ;;
    http://*)
      [ "${COOKIE_SECURE:-false}" = "false" ] || {
        echo "ERROR: bootstrap mode served over HTTP requires COOKIE_SECURE=false"
        fail=1
      }
      if [ "${SHARED_HTTP_EDGE:-false}" = "true" ]; then
        echo "ERROR: bootstrap mode behind the shared HTTP edge must use an https:// FRONTEND_URL"
        fail=1
      fi
      ;;
    *)
      echo "ERROR: FRONTEND_URL must be an HTTP(S) URL"
      fail=1
      ;;
  esac
  [ "${MAIL_TLS_MODE:-selfsigned}" = "selfsigned" ] || {
    echo "ERROR: bootstrap mode must use MAIL_TLS_MODE=selfsigned until the platform domain is activated"
    fail=1
  }
else
  [ "${COOKIE_SECURE:-}" = "true" ] || { echo "ERROR: domain mode requires COOKIE_SECURE=true"; fail=1; }
  case "${MAIL_TLS_MODE:-}" in
    acme|external) ;;
    *) echo "ERROR: domain mode requires MAIL_TLS_MODE=acme or external"; fail=1 ;;
  esac

  for name in PANEL_HOSTNAME API_HOSTNAME GROUPWARE_HOSTNAME ACME_EMAIL MAIL_HOSTNAME NAMESERVER_1 NAMESERVER_2 SYSTEM_EMAIL_FROM SYSTEM_SMTP_HOST; do
    require "$name"
  done

  case "${GROUPWARE_PUBLIC_URL:-}" in
    https://*) ;;
    *) echo "ERROR: GROUPWARE_PUBLIC_URL must use https:// in domain production mode"; fail=1 ;;
  esac
  case "${FRONTEND_URL:-}" in
    https://*) ;;
    *) echo "ERROR: FRONTEND_URL must use https:// in domain production mode"; fail=1 ;;
  esac
  if [ "${SYSTEM_SMTP_SSL:-false}" != "true" ] && [ "${SYSTEM_SMTP_STARTTLS:-true}" != "true" ]; then
    echo "ERROR: system SMTP must use SSL or STARTTLS in domain production mode"
    fail=1
  fi
fi

if [ -n "${DPO_COMPANY_TOKEN:-}" ]; then
  require DPO_SERVICE_TYPE
  case "${DPO_API_URL:-}" in https://*) ;; *) echo "ERROR: DPO_API_URL must use https://"; fail=1 ;; esac
  case "${DPO_CHECKOUT_URL:-}" in https://*) ;; *) echo "ERROR: DPO_CHECKOUT_URL must use https://"; fail=1 ;; esac
  case "${DPO_REDIRECT_URL:-}" in https://*) ;; *) echo "ERROR: DPO_REDIRECT_URL must use https:// when DPO is enabled"; fail=1 ;; esac
  case "${DPO_BACK_URL:-}" in https://*) ;; *) echo "ERROR: DPO_BACK_URL must use https:// when DPO is enabled"; fail=1 ;; esac
fi

if [ -n "${OPENSRS_USERNAME:-}" ]; then
  require OPENSRS_API_KEY
fi

if [ "${HA_MAIL_ENABLED:-false}" = "true" ]; then
  require MAIL_EDGE_NODE1_HOST
  require MAIL_EDGE_NODE2_HOST
  require DOVECOT_REPLICATION_PASSWORD
  case "${DOVECOT_REPLICATION_PASSWORD:-}" in
    *replace*|*development*|"")
      echo "ERROR: DOVECOT_REPLICATION_PASSWORD must be a strong independent secret"
      fail=1
      ;;
  esac
  [ "${SMTP_PORT:-25}" != "25" ] || { echo "ERROR: HA mode reserves host port 25 for mail-edge; move local Postfix SMTP_PORT to a high/private port"; fail=1; }
  [ "${SUBMISSION_PORT:-587}" != "587" ] || { echo "ERROR: HA mode reserves host port 587 for mail-edge"; fail=1; }
  [ "${IMAPS_PORT:-993}" != "993" ] || { echo "ERROR: HA mode reserves host port 993 for mail-edge"; fail=1; }
fi

[ "$fail" -eq 0 ] || { echo "Production preflight FAILED."; exit 1; }

echo "Production preflight PASSED (${PLATFORM_MODE:-bootstrap} mode, central Auth/Push enabled)."
