FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN set -eux; \
    for attempt in 1 2 3; do \
        pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt && break; \
        if [ "$attempt" -eq 3 ]; then \
            echo "pip install failed after 3 attempts" >&2; \
            exit 1; \
        fi; \
        echo "pip install failed (attempt ${attempt}/3); retrying in 10 seconds..." >&2; \
        sleep 10; \
    done

COPY --chown=appuser:appuser . .

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
