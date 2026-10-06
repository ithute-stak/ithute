from __future__ import annotations

import json
import os
import signal
import time

from app.db.session import SessionLocal
from app.services.hardware_notifications import dispatch_hardware_incident_deliveries

_running = True


def _stop(*_args) -> None:
    global _running
    _running = False


def _interval_seconds() -> int:
    try:
        return max(10, min(int(os.getenv("HARDWARE_NOTIFICATION_POLL_SECONDS", "20")), 300))
    except ValueError:
        return 20


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    interval = _interval_seconds()

    while _running:
        db = SessionLocal()
        try:
            result = dispatch_hardware_incident_deliveries(db)
            print(
                json.dumps(
                    {"event": "hardware_incident_delivery_dispatch", **result},
                    sort_keys=True,
                ),
                flush=True,
            )
        except Exception as exc:
            db.rollback()
            print(
                json.dumps(
                    {
                        "event": "hardware_incident_delivery_dispatch_error",
                        "error": exc.__class__.__name__,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        finally:
            db.close()

        slept = 0
        while _running and slept < interval:
            time.sleep(1)
            slept += 1


if __name__ == "__main__":
    main()
