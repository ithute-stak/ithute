FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 ithute && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin ithute
COPY --chown=10001:10001 . .
RUN chmod +x /app/entrypoint.sh
USER 10001:10001

EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
