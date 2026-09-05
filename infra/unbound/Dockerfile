FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends unbound dnsutils ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY unbound.conf /etc/unbound/unbound.conf

EXPOSE 53/udp 53/tcp

HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=10s \
  CMD dig @127.0.0.1 . SOA +time=2 +tries=1 >/dev/null 2>&1 || exit 1

ENTRYPOINT ["unbound", "-d", "-c", "/etc/unbound/unbound.conf"]
