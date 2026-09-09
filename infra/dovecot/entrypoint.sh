#!/usr/bin/env sh
set -eu

: "${POSTGRES_DB:=lelefamail}"
: "${POSTGRES_USER:=lelefamail}"
: "${POSTGRES_PASSWORD:=lelefamail_dev_password}"
: "${MAIL_TLS_MODE:=selfsigned}"
: "${MAIL_TLS_CERT_PATH:=/etc/dovecot/tls/cert.pem}"
: "${MAIL_TLS_KEY_PATH:=/etc/dovecot/tls/key.pem}"
: "${MAIL_TLS_RELOAD_INTERVAL_SECONDS:=300}"

mkdir -p /srv/vmail
chown -R vmail:vmail /srv/vmail

case "$MAIL_TLS_MODE" in
  selfsigned)
    mkdir -p "$(dirname "$MAIL_TLS_CERT_PATH")" "$(dirname "$MAIL_TLS_KEY_PATH")"
    if [ ! -s "$MAIL_TLS_CERT_PATH" ] || [ ! -s "$MAIL_TLS_KEY_PATH" ]; then
      openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
        -subj "/CN=${MAIL_HOSTNAME:-mail.phase8.test}" \
        -addext "subjectAltName=DNS:${MAIL_HOSTNAME:-mail.phase8.test}" \
        -keyout "$MAIL_TLS_KEY_PATH" \
        -out "$MAIL_TLS_CERT_PATH" >/dev/null 2>&1
      chmod 600 "$MAIL_TLS_KEY_PATH"
    fi
    ;;
  acme|external)
    if [ ! -s "$MAIL_TLS_CERT_PATH" ] || [ ! -s "$MAIL_TLS_KEY_PATH" ]; then
      echo "MAIL_TLS_MODE=$MAIL_TLS_MODE requires Dovecot certificate and key at $MAIL_TLS_CERT_PATH and $MAIL_TLS_KEY_PATH" >&2
      exit 1
    fi
    ;;
  *)
    echo "MAIL_TLS_MODE must be selfsigned, acme, or external" >&2
    exit 1
    ;;
esac

# Keep one canonical public hostname/certificate for every customer mailbox.
# Production mounts the shared ithute-edge Let's Encrypt certificate read-only;
# development can continue to use the isolated self-signed certificate.
sed -i "s|^ssl_cert = .*|ssl_cert = <$MAIL_TLS_CERT_PATH|" /etc/dovecot/dovecot.conf
sed -i "s|^ssl_key = .*|ssl_key = <$MAIL_TLS_KEY_PATH|" /etc/dovecot/dovecot.conf

cat > /etc/dovecot/dovecot-sql.conf.ext <<EOF
driver = pgsql
connect = host=postgres dbname=${POSTGRES_DB} user=${POSTGRES_USER} password=${POSTGRES_PASSWORD}
default_pass_scheme = SHA512-CRYPT
password_query = SELECT q.user, q.password FROM (SELECT m.address AS user, m.password_hash AS password, 1 AS priority FROM mailboxes m JOIN domains d ON d.id=m.domain_id JOIN tenants t ON t.id=m.tenant_id WHERE lower(m.address)=lower('%u') AND m.status='active' AND d.status='verified' AND d.mail_enabled=true AND t.status='active' UNION ALL SELECT sc.username AS user, sc.password_hash AS password, 2 AS priority FROM smtp_credentials sc JOIN tenants t ON t.id=sc.tenant_id WHERE '%s'='smtp' AND lower(sc.username)=lower('%u') AND sc.active=true AND t.status='active') q ORDER BY q.priority LIMIT 1
user_query = SELECT 5000 AS uid, 5000 AS gid, '/srv/vmail/' || split_part(m.address,'@',2) || '/' || split_part(m.address,'@',1) AS home, 'maildir:/srv/vmail/' || split_part(m.address,'@',2) || '/' || split_part(m.address,'@',1) || '/Maildir' AS mail, '*:bytes=' || m.quota_bytes::text AS quota_rule FROM mailboxes m JOIN domains d ON d.id=m.domain_id JOIN tenants t ON t.id=m.tenant_id WHERE lower(m.address)=lower('%u') AND m.status='active' AND d.status='verified' AND d.mail_enabled=true AND t.status='active' LIMIT 1
iterate_query = SELECT m.address AS username FROM mailboxes m JOIN domains d ON d.id=m.domain_id JOIN tenants t ON t.id=m.tenant_id WHERE m.status='active' AND d.status='verified' AND d.mail_enabled=true AND t.status='active'
EOF
chown root:dovecot /etc/dovecot/dovecot-sql.conf.ext
chmod 640 /etc/dovecot/dovecot-sql.conf.ext

if [ -n "${DOVECOT_REPLICATION_PEER:-}" ]; then
  : "${DOVECOT_REPLICATION_PASSWORD:?DOVECOT_REPLICATION_PASSWORD is required when replication is enabled}"
  sed -i 's/^mail_plugins = quota acl$/mail_plugins = quota acl notify replication/' /etc/dovecot/dovecot.conf
  sed -i "/^  sieve =/a\  mail_replica = tcp:${DOVECOT_REPLICATION_PEER}:24245" /etc/dovecot/dovecot.conf
  cat >> /etc/dovecot/dovecot.conf <<EOF

doveadm_password = ${DOVECOT_REPLICATION_PASSWORD}
service aggregator {
  fifo_listener replication-notify-fifo {
    user = vmail
  }
  unix_listener replication-notify {
    user = vmail
  }
}
service replicator {
  process_min_avail = 1
  unix_listener replicator-doveadm {
    mode = 0600
  }
}
service doveadm {
  inet_listener replication {
    port = 24245
  }
}
EOF
fi

watch_tls_certificate() {
  previous="$(sha256sum "$MAIL_TLS_CERT_PATH" 2>/dev/null | awk '{print $1}')"
  while sleep "$MAIL_TLS_RELOAD_INTERVAL_SECONDS"; do
    current="$(sha256sum "$MAIL_TLS_CERT_PATH" 2>/dev/null | awk '{print $1}')"
    if [ -n "$current" ] && [ "$current" != "$previous" ]; then
      if doveadm reload; then
        echo "Reloaded Dovecot after TLS certificate renewal"
        previous="$current"
      fi
    fi
  done
}

doveconf -n >/dev/null
case "$MAIL_TLS_MODE" in
  acme|external) watch_tls_certificate & ;;
esac
exec dovecot -F
