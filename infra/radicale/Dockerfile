FROM python:3.12-alpine

RUN pip install --no-cache-dir "radicale==3.7.8" "passlib[bcrypt]==1.7.4" "bcrypt==4.0.1"
COPY config /etc/radicale/config
COPY entrypoint.sh /usr/local/bin/mailbox-radicale-entrypoint
RUN mkdir -p /var/lib/radicale/collections /auth \
    && chmod 0755 /usr/local/bin/mailbox-radicale-entrypoint
EXPOSE 5232
ENTRYPOINT ["/usr/local/bin/mailbox-radicale-entrypoint"]
CMD ["radicale", "--config", "/etc/radicale/config"]
