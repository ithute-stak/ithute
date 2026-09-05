#!/usr/bin/env sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 /path/to/fullchain.pem /path/to/privkey.pem" >&2
  exit 2
fi

CERT="$1"
KEY="$2"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml"

[ -s "$CERT" ] || { echo "Certificate not found: $CERT" >&2; exit 1; }
[ -s "$KEY" ] || { echo "Private key not found: $KEY" >&2; exit 1; }

openssl x509 -in "$CERT" -noout >/dev/null
openssl pkey -in "$KEY" -noout >/dev/null
CERT_PUB="$(openssl x509 -in "$CERT" -pubkey -noout | openssl pkey -pubin -outform der | sha256sum | awk '{print $1}')"
KEY_PUB="$(openssl pkey -in "$KEY" -pubout -outform der | sha256sum | awk '{print $1}')"
[ "$CERT_PUB" = "$KEY_PUB" ] || { echo "Certificate and private key do not match" >&2; exit 1; }

$COMPOSE cp "$CERT" postfix:/etc/postfix/tls/cert.pem
$COMPOSE cp "$KEY" postfix:/etc/postfix/tls/key.pem
$COMPOSE exec -T postfix chmod 600 /etc/postfix/tls/key.pem
$COMPOSE exec -T postfix postfix reload

$COMPOSE cp "$CERT" dovecot:/etc/dovecot/tls/cert.pem
$COMPOSE cp "$KEY" dovecot:/etc/dovecot/tls/key.pem
$COMPOSE exec -T dovecot chmod 600 /etc/dovecot/tls/key.pem
$COMPOSE exec -T dovecot doveadm reload

$COMPOSE exec -T postfix openssl x509 -in /etc/postfix/tls/cert.pem -noout -subject -issuer -enddate
$COMPOSE exec -T dovecot openssl x509 -in /etc/dovecot/tls/cert.pem -noout -subject -issuer -enddate

echo "Mail TLS certificate deployed and Postfix/Dovecot reloaded successfully."
