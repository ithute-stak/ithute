#!/usr/bin/env sh
set -eu

: "${POSTGRES_DB:=lelefamail}"
: "${POSTGRES_USER:=lelefamail}"
: "${POSTGRES_PASSWORD:=lelefamail_dev_password}"
: "${MAIL_OPS_TOKEN:=development-mail-ops-token-change-me}"
: "${MAIL_TLS_MODE:=selfsigned}"
: "${MAIL_TLS_CERT_PATH:=/etc/postfix/tls/cert.pem}"
: "${MAIL_TLS_KEY_PATH:=/etc/postfix/tls/key.pem}"
: "${MAIL_TLS_RELOAD_INTERVAL_SECONDS:=300}"

mkdir -p "$(dirname "$MAIL_TLS_CERT_PATH")" "$(dirname "$MAIL_TLS_KEY_PATH")"
case "$MAIL_TLS_MODE" in
  selfsigned)
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
      echo "MAIL_TLS_MODE=$MAIL_TLS_MODE requires certificate and key at $MAIL_TLS_CERT_PATH and $MAIL_TLS_KEY_PATH" >&2
      exit 1
    fi
    ;;
  *)
    echo "MAIL_TLS_MODE must be selfsigned, acme, or external" >&2
    exit 1
    ;;
esac

write_pgsql_map() {
  path="$1"
  query="$2"
  cat > "$path" <<EOF
hosts = postgres
user = ${POSTGRES_USER}
password = ${POSTGRES_PASSWORD}
dbname = ${POSTGRES_DB}
query = ${query}
EOF
  chown root:postfix "$path"
  chmod 640 "$path"
}

write_pgsql_map /etc/postfix/pgsql-virtual-domains.cf "SELECT 1 FROM domains d JOIN tenants t ON t.id=d.tenant_id WHERE lower(d.ascii_name)=lower('%s') AND d.status='verified' AND d.mail_enabled=true AND t.status='active' LIMIT 1"
write_pgsql_map /etc/postfix/pgsql-virtual-mailboxes.cf "SELECT 1 FROM mailboxes m JOIN domains d ON d.id=m.domain_id JOIN tenants t ON t.id=m.tenant_id WHERE lower(m.address)=lower('%s') AND m.status='active' AND d.status='verified' AND d.mail_enabled=true AND t.status='active' LIMIT 1"
write_pgsql_map /etc/postfix/pgsql-virtual-aliases.cf "SELECT string_agg(a.destination_address, ',') FROM mail_aliases a JOIN domains d ON d.id=a.domain_id JOIN tenants t ON t.id=a.tenant_id WHERE lower(a.source_address)=lower('%s') AND a.active=true AND d.status='verified' AND d.mail_enabled=true AND t.status='active' HAVING count(*) > 0"
write_pgsql_map /etc/postfix/pgsql-distribution-groups.cf "SELECT string_agg(m.destination_address, ',') FROM distribution_groups g JOIN distribution_group_members m ON m.group_id=g.id JOIN domains d ON d.id=g.domain_id JOIN tenants t ON t.id=g.tenant_id WHERE lower(g.address)=lower('%s') AND g.active=true AND d.status='verified' AND d.mail_enabled=true AND t.status='active' HAVING count(*) > 0"
write_pgsql_map /etc/postfix/pgsql-sender-login.cf "SELECT COALESCE((SELECT string_agg(owner, ',') FROM (SELECT lower(m.address) AS owner FROM mailboxes m JOIN domains d ON d.id=m.domain_id JOIN tenants t ON t.id=m.tenant_id WHERE lower(m.address)=lower('%s') AND m.status='active' AND d.status='verified' AND d.mail_enabled=true AND t.status='active' UNION SELECT lower(a.destination_address) AS owner FROM mail_aliases a JOIN domains d ON d.id=a.domain_id JOIN tenants t ON t.id=a.tenant_id JOIN mailboxes m ON lower(m.address)=lower(a.destination_address) AND m.tenant_id=a.tenant_id WHERE lower(a.source_address)=lower('%s') AND a.active=true AND m.status='active' AND d.status='verified' AND d.mail_enabled=true AND t.status='active' UNION SELECT lower(sc.username) AS owner FROM smtp_credentials sc JOIN tenants t ON t.id=sc.tenant_id JOIN domains d ON d.tenant_id=sc.tenant_id WHERE lower(d.ascii_name)=lower(split_part('%s','@',2)) AND d.status='verified' AND d.mail_enabled=true AND t.status='active' AND sc.active=true AND (sc.system_managed=true OR sc.sender_address IS NULL OR lower(sc.sender_address)=lower('%s'))) owners), '__mailbox_dns_unowned_sender__')"

postconf -e "myhostname=${MAIL_HOSTNAME:-mail.phase8.test}"
postconf -e "smtpd_tls_cert_file=$MAIL_TLS_CERT_PATH"
postconf -e "smtpd_tls_key_file=$MAIL_TLS_KEY_PATH"
postconf -e 'smtpd_sender_login_maps=pgsql:/etc/postfix/pgsql-sender-login.cf'
postconf -e 'maillog_file=/dev/stdout'
postconf -e 'smtpd_tls_mandatory_protocols=>=TLSv1.2'
postconf -e 'smtp_tls_mandatory_protocols=>=TLSv1.2'
# Debian defaults both the public smtp listener and outbound smtp transport to
# chrooted master services. Inside this container that hides Docker's runtime
# resolver state, breaking Rspamd service discovery on inbound mail and public
# MX lookups on outbound mail. The container is the isolation boundary, so keep
# both SMTP directions non-chrooted while leaving all filtering and TLS enabled.
postconf -M 'smtp/inet=smtp inet n - n - - smtpd'
postconf -M 'smtp/unix=smtp unix - - n - - smtp'
# Keep the policy expression in main.cf because postconf -P rejects whitespace in
# a master.cf parameter value. The submission override itself remains one token,
# so the rate policy applies only to authenticated submission and not inbound MX.
postconf -e 'mailbox_dns_submission_eod_restrictions=check_policy_service { inet:smtp-policy:10031, timeout=5s, default_action=DUNNO }'
postconf -M 'submission/inet=submission inet n - n - - smtpd'
postconf -P 'submission/inet/syslog_name=postfix/submission'
postconf -P 'submission/inet/smtpd_tls_security_level=encrypt'
postconf -P 'submission/inet/smtpd_sasl_auth_enable=yes'
postconf -P 'submission/inet/smtpd_relay_restrictions=permit_sasl_authenticated,reject'
postconf -P 'submission/inet/smtpd_sender_restrictions=reject_authenticated_sender_login_mismatch'
postconf -P 'submission/inet/smtpd_end_of_data_restrictions=$mailbox_dns_submission_eod_restrictions'
postconf -M 'rewrite/unix=rewrite unix - - n - - trivial-rewrite'
postconf -M 'cleanup/unix=cleanup unix n - n - 0 cleanup'
postconf -M 'lmtp/unix=lmtp unix - - n - - lmtp'

watch_tls_certificate() {
  previous="$(sha256sum "$MAIL_TLS_CERT_PATH" 2>/dev/null | awk '{print $1}')"
  while sleep "$MAIL_TLS_RELOAD_INTERVAL_SECONDS"; do
    current="$(sha256sum "$MAIL_TLS_CERT_PATH" 2>/dev/null | awk '{print $1}')"
    if [ -n "$current" ] && [ "$current" != "$previous" ]; then
      if postfix reload; then
        echo "Reloaded Postfix after TLS certificate renewal"
        previous="$current"
      fi
    fi
  done
}

postfix check
case "$MAIL_TLS_MODE" in
  acme|external) watch_tls_certificate & ;;
esac
MAIL_OPS_TOKEN="$MAIL_OPS_TOKEN" MAIL_OPS_PORT="${MAIL_OPS_PORT:-9080}" MAIL_HOSTNAME="${MAIL_HOSTNAME:-mail.phase8.test}" MAIL_TLS_CERT_PATH="$MAIL_TLS_CERT_PATH" /usr/local/bin/mailbox-mail-ops &
exec postfix start-fg
