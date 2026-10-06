from __future__ import annotations

import json
import os
import signal
import time

from app.db.session import SessionLocal
from app.services.hosting_node_health import run_hosting_node_health_reconcile
from app.services.hosting_failover import run_application_failover_reconcile
from app.services.postgres_rto_slo import reconcile_postgres_auto_failover
from app.services.database_gateway_ha import reconcile_database_gateway_health

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
            failover = run_application_failover_reconcile(db)
            print(json.dumps({"event": "hosting_application_failover_reconcile", **failover}, sort_keys=True), flush=True)
            postgres_failover = reconcile_postgres_auto_failover(db)
            print(json.dumps({"event": "hosting_postgres_auto_failover_reconcile", **postgres_failover}, sort_keys=True), flush=True)
            gateway_health = reconcile_database_gateway_health(db)
            print(json.dumps({"event": "hosting_database_gateway_ha_reconcile", **gateway_health}, sort_keys=True), flush=True)
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
