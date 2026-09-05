FROM haproxy:3.1-alpine
USER root
COPY entrypoint.sh /usr/local/bin/mailbox-mail-edge
RUN chmod 0755 /usr/local/bin/mailbox-mail-edge
USER haproxy
ENTRYPOINT ["/usr/local/bin/mailbox-mail-edge"]
