#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

python -m py_compile \
  apps/backend/app/models/ithute_operating.py \
  apps/backend/app/models/mail_intelligence.py \
  apps/backend/app/services/ithute_operating.py \
  apps/backend/app/api/v1/ithute_operating_common.py \
  apps/backend/app/api/v1/ithute_operating_control.py \
  apps/backend/app/api/v1/ithute_operating_events.py \
  apps/backend/app/api/v1/ithute_operating_ops.py \
  apps/backend/app/api/v1/ithute_operating.py \
  apps/backend/app/api/v1/mail_intelligence.py \
  apps/backend/alembic/versions/0013_ithute_operating_core.py \
  apps/backend/alembic/versions/0014_ithute_operating_ops.py \
  apps/backend/alembic/versions/0015_mail_intelligence.py

test -s product.manifest.yaml
python - <<'PYCODE'
from pathlib import Path

content = Path("apps/backend/app/services/ithute_operating.py").read_text(encoding="utf-8")
for repository in (
    "https://github.com/ithute-stak/LoanHub",
    "https://github.com/ithute-stak/ithute-pay",
    "https://github.com/ithute-stak/ithute-tutor",
):
    assert repository in content, repository
assert "source_path\": \"products/" not in content
PYCODE

if git grep -nE 'products/(LoanHub|ithute-pay|ithute-tutor|nbros)' --   ':!.github/**'; then
  echo 'Extracted product source path remains in the Ithute platform repository.' >&2
  exit 1
fi

echo 'Ithute operating-platform static validation passed.'
