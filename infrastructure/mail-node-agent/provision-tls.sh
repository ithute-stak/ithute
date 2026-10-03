#!/usr/bin/env bash
set -euo pipefail

: "${ITHUTE_MAIL_HOSTNAME:?Set ITHUTE_MAIL_HOSTNAME}"
: "${ITHUTE_TLS_EMAIL:?Set ITHUTE_TLS_EMAIL for Let's Encrypt notices}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root." >&2
  exit 2
fi
command -v certbot >/dev/null 2>&1 || {
  echo "certbot must be installed first." >&2
  exit 2
}

if docker inspect ithute-mail >/dev/null 2>&1; then
  docker stop --time 30 ithute-mail >/dev/null
  trap 'docker start ithute-mail >/dev/null 2>&1 || true' EXIT
fi

certbot certonly   --standalone   --non-interactive   --agree-tos   --preferred-challenges http   --email "$ITHUTE_TLS_EMAIL"   -d "$ITHUTE_MAIL_HOSTNAME"

install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/ithute-mail-node <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
docker restart ithute-mail >/dev/null 2>&1 || true
HOOK
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/ithute-mail-node

if docker inspect ithute-mail >/dev/null 2>&1; then
  docker start ithute-mail >/dev/null
fi
trap - EXIT

echo "TLS certificate installed for $ITHUTE_MAIL_HOSTNAME."
