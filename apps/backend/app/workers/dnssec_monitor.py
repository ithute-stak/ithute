"""Opt-in DNSSEC monitoring entrypoint for an external scheduler.

Example: python -m app.workers.dnssec_monitor
The deployment scheduler should invoke it at a controlled cadence. This
entrypoint does not change DNS records, registrars or signing keys.
"""
from __future__ import annotations

import logging
import os

from app.db.session import SessionLocal
from app.services.dnssec_monitor_runner import run_dnssec_monitor

logger = logging.getLogger(__name__)


def main() -> int:
    if os.getenv("ITHUTE_DNSSEC_MONITOR_ENABLED", "").lower() not in {"1", "true", "yes"}:
        logger.info("DNSSEC monitoring is disabled; set ITHUTE_DNSSEC_MONITOR_ENABLED=true to opt in")
        return 0
    try:
        limit = int(os.getenv("ITHUTE_DNSSEC_MONITOR_BATCH_SIZE", "100"))
        with SessionLocal() as db:
            outcome = run_dnssec_monitor(db, limit=limit)
        logger.info("DNSSEC monitor outcome: %s", outcome)
        return 1 if outcome.get("failed") else 0
    except Exception:
        logger.exception("DNSSEC monitor failed")
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
