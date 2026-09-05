FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && echo 'postfix postfix/mailname string mail.phase8.test' | debconf-set-selections \
    && echo 'postfix postfix/main_mailer_type string Internet Site' | debconf-set-selections \
    && apt-get install -y --no-install-recommends postfix postfix-pgsql ca-certificates openssl netcat-openbsd python3 \
    && rm -rf /var/lib/apt/lists/*

COPY main.cf /etc/postfix/main.cf
COPY entrypoint.sh /usr/local/bin/mailbox-postfix-entrypoint
COPY mail_ops_server.py /usr/local/bin/mailbox-mail-ops
RUN chmod +x /usr/local/bin/mailbox-postfix-entrypoint /usr/local/bin/mailbox-mail-ops

EXPOSE 25 587 9080
ENTRYPOINT ["/usr/local/bin/mailbox-postfix-entrypoint"]
