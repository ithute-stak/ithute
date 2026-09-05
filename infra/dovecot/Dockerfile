FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends dovecot-core dovecot-imapd dovecot-lmtpd dovecot-pgsql dovecot-sieve ca-certificates openssl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 5000 vmail \
    && useradd -u 5000 -g 5000 -d /srv/vmail -s /usr/sbin/nologin vmail

COPY dovecot.conf /etc/dovecot/dovecot.conf
COPY entrypoint.sh /usr/local/bin/mailbox-dovecot-entrypoint
RUN chmod +x /usr/local/bin/mailbox-dovecot-entrypoint

EXPOSE 143 993 24 12345
ENTRYPOINT ["/usr/local/bin/mailbox-dovecot-entrypoint"]
