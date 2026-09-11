from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from redis import Redis
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .fleet_alerts import FleetAlert, sync_vehicle_alerts
from .fleet_engine import evaluate_vehicle
from .fleet_inventory import vehicle_service_kit_stock
from .models import BranchModule, Profile, ProfileBranchAccess, Vehicle
from .realtime_publisher import publisher

log = logging.getLogger("nbros.fleet_monitor")
logging.basicConfig(level=logging.INFO)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def recipient_subs(db, branch_id: uuid.UUID) -> list[str]:
    admin_ids = set(db.scalars(select(Profile.auth_user_id).where(Profile.role.in_(["admin", "fleet_admin"]))))
    branch_ids = set(db.scalars(select(Profile.auth_user_id).join(ProfileBranchAccess, ProfileBranchAccess.profile_id == Profile.id).where(ProfileBranchAccess.branch_id == branch_id)))
    return sorted(str(value) for value in admin_ids | branch_ids)


def monitor_once(redis_client: Redis) -> dict[str, int | str]:
    token = str(uuid.uuid4())
    lock_key = "nbros:fleet-monitor:lock"
    lock_seconds = max(settings.fleet_monitor_lock_seconds, settings.fleet_monitor_interval_seconds * 2, 30)
    if not redis_client.set(lock_key, token, nx=True, ex=lock_seconds):
        return {"status": "locked", "vehicles": 0, "notifications": 0}
    vehicles_checked = 0
    notifications_sent = 0
    notification_failures = 0
    now = utcnow()
    pending_notifications: list[dict[str, str | list[str]]] = []
    try:
        with SessionLocal() as db:
            branch_ids = select(BranchModule.branch_id).where(BranchModule.module_key == "fleet", BranchModule.is_enabled.is_(True))
            vehicles = list(db.scalars(select(Vehicle).where(Vehicle.is_active.is_(True), Vehicle.branch_id.in_(branch_ids))))
            for vehicle in vehicles:
                snapshot = evaluate_vehicle(db, vehicle, at=now)
                snapshot["inventory"] = vehicle_service_kit_stock(db, vehicle, service_snapshot=snapshot.get("service"))
                changed_rows = sync_vehicle_alerts(db, branch_id=vehicle.branch_id, vehicle_id=vehicle.id, snapshot=snapshot, now=now)
                vehicles_checked += 1
                recipients = recipient_subs(db, vehicle.branch_id)
                for row in changed_rows:
                    pending_notifications.append({"recipient_subs": recipients, "alert_id": str(row.id), "branch_id": str(vehicle.branch_id), "vehicle_id": str(vehicle.id), "registration_plate": vehicle.registration_plate, "severity": row.severity, "label": row.label, "detail": row.detail, "source_type": row.source_type, "source_id": row.source_id, "fingerprint": row.fingerprint})
            db.commit()

            for item in pending_notifications:
                row = db.get(FleetAlert, uuid.UUID(str(item["alert_id"])))
                if row is None:
                    continue
                row.notification_attempts += 1
                try:
                    sent = publisher.publish_fleet_alert(**item)
                    if sent:
                        notifications_sent += 1
                        row.last_notified_at = now
                        row.last_notification_error = None
                    else:
                        notification_failures += 1
                        row.last_notification_error = "Realtime publisher reported no delivery."
                except Exception as exc:
                    notification_failures += 1
                    row.last_notification_error = str(exc)[:2000] or exc.__class__.__name__
                    log.exception("Failed to publish fleet alert %s", item["alert_id"])
            db.commit()

        result = {
            "status": "ok",
            "vehicles": vehicles_checked,
            "notifications": notifications_sent,
            "notification_failures": notification_failures,
            "evaluated_at": now.isoformat(),
        }
        redis_client.set("nbros:fleet-monitor:last-run", json.dumps(result), ex=86400)
        return result
    finally:
        current = redis_client.get(lock_key)
        if current and current.decode("utf-8") == token:
            redis_client.delete(lock_key)


def main() -> None:
    redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
    interval = max(settings.fleet_monitor_interval_seconds, 15)
    log.info("NBros Fleet monitor started; interval=%ss", interval)
    while True:
        started = time.monotonic()
        try:
            log.info("Fleet monitor result: %s", monitor_once(redis_client))
        except Exception:
            log.exception("Fleet monitor cycle failed")
        time.sleep(max(interval - (time.monotonic() - started), 1))


if __name__ == "__main__":
    main()
