#!/bin/sh
set -eu

cd /app
export PYTHONPATH="/app${PYTHONPATH:+:$PYTHONPATH}"

python - <<'PY'
import time
from sqlalchemy import text
from database.session import engine

last_error = None
for _ in range(60):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        break
    except Exception as exc:
        last_error = exc
        time.sleep(2)
else:
    raise SystemExit(f"Tutor database did not become ready: {last_error}")
PY

# Existing Tutor history contains multiple migration branches; upgrading all
# heads is safer than choosing a single head and silently skipping schema work.
alembic upgrade heads
python -m scripts.ensure_central_auth_schema
python -m scripts.ensure_academic_core_schema
python -m scripts.ensure_student_transfer_schema
python -m scripts.ensure_learning_exchange_schema

exec uvicorn main:app --host 0.0.0.0 --port 8000
