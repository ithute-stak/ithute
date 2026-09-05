#!/usr/bin/env sh
set -eu

: "${POSTGRES_DB:=lelefamail}"
: "${POSTGRES_USER:=lelefamail}"
: "${POSTGRES_PASSWORD:=lelefamail_dev_password}"
: "${MAIL_TLS_MODE:=selfsigned}"

mkdir -p /etc/dovecot/tls /srv/vmail
chown -R vmail:vmail /srv/vmail

if [ ! -s /etc/dovecot/tls/cert.pem ] || [ ! -s /etc/dovecot/tls/key.pem ]; then
  if [ "$MAIL_TLS_MODE" != "selfsigned" ]; then
    echo "MAIL_TLS_MODE=$MAIL_TLS_MODE requires Dovecot certificate and key" >&2
    exit 1
  fi
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
    -subj "/CN=${MAIL_HOSTNAME:-mail.phase8.test}" \
    -addext "subjectAltName=DNS:${MAIL_HOSTNAME:-mail.phase8.test}" \
    -keyout /etc/dovecot/tls/key.pem \
    -out /etc/dovecot/tls/cert.pem >/dev/null 2>&1
  chmod 600 /etc/dovecot/tls/key.pem
fi

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

doveconf -n >/dev/null
exec dovecot -F
