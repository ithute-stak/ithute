from __future__ import annotations

import json

from app.db.session import SessionLocal
from app.services.domain_health_monitor import run_domain_health_monitor


def main() -> None:
    db = SessionLocal()
    try:
        result = run_domain_health_monitor(db)
        print(json.dumps(result, sort_keys=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
