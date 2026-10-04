from __future__ import annotations

import json
import os
import signal
import time

from app.db.session import SessionLocal
from app.services.hosting_node_health import run_hosting_node_health_reconcile

_running = True


def _stop(*_args) -> None:
    global _running
    _running = False


def main() -> None:
    interval = max(15, min(int(os.getenv("ITHUTE_HOSTING_HEALTH_RECONCILE_SECONDS", "30")), 300))
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while _running:
        db = SessionLocal()
        try:
            result = run_hosting_node_health_reconcile(db)
            print(json.dumps({"event": "hosting_node_health_reconcile", **result}, sort_keys=True), flush=True)
        except Exception as exc:
            db.rollback()
            print(json.dumps({"event": "hosting_node_health_reconcile_error", "error": exc.__class__.__name__}, sort_keys=True), flush=True)
        finally:
            db.close()

        slept = 0
        while _running and slept < interval:
            time.sleep(1)
            slept += 1


if __name__ == "__main__":
    main()
