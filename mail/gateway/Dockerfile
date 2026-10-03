FROM alpine:3.22

RUN apk add --no-cache postfix ca-certificates

COPY main.cf /etc/postfix/main.cf
COPY entrypoint.sh /usr/local/bin/ithute-mail-gateway

RUN chmod 0755 /usr/local/bin/ithute-mail-gateway

EXPOSE 25

ENTRYPOINT ["/usr/local/bin/ithute-mail-gateway"]
