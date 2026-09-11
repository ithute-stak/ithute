from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FleetAlert(Base):
    __tablename__ = "fleet_alerts"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "alert_key", name="uq_fleet_alert_vehicle_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_key: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _candidate(component: str, item: dict[str, Any], vehicle_id: uuid.UUID) -> dict[str, str]:
    source_type = str(item.get("source_type") or "vehicle")
    source_id = str(item.get("source_id") or vehicle_id)
    label = str(item.get("label") or "FLEET ATTENTION")
    detail = str(item.get("detail") or label)
    severity = str(item.get("level") or "orange")
    identity = f"{source_type}|{source_id}|{label}".lower()
    alert_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    fingerprint = hashlib.sha256(
        f"{severity}|{label}|{detail}|{source_type}|{source_id}".encode("utf-8")
    ).hexdigest()
    return {
        "alert_key": alert_key,
        "severity": severity,
        "label": label,
        "detail": detail,
        "source_type": source_type,
        "source_id": source_id,
        "fingerprint": fingerprint,
    }


def snapshot_alert_candidates(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    vehicle_id = uuid.UUID(str(snapshot["vehicle"]["id"]))
    candidates: list[dict[str, str]] = []

    for item in snapshot.get("documents", {}).get("items", []):
        if item.get("level") != "green":
            candidates.append(_candidate("documents", item, vehicle_id))

    for component in ("service", "mechanical", "inspection"):
        item = snapshot.get(component)
        if isinstance(item, dict) and item.get("level") != "green":
            candidates.append(_candidate(component, item, vehicle_id))

    for blocker in snapshot.get("availability", {}).get("blockers", []):
        if isinstance(blocker, dict):
            candidates.append(_candidate("availability", blocker, vehicle_id))

    deduped: dict[str, dict[str, str]] = {}
    for item in candidates:
        deduped[item["alert_key"]] = item
    return list(deduped.values())


def sync_vehicle_alerts(
    db: Session,
    *,
    branch_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    snapshot: dict[str, Any],
    now: datetime | None = None,
) -> list[FleetAlert]:
    now = now or utcnow()
    rows = list(
        db.scalars(select(FleetAlert).where(FleetAlert.vehicle_id == vehicle_id))
    )
    rows_by_key = {row.alert_key: row for row in rows}
    seen: set[str] = set()
    notify: list[FleetAlert] = []

    for item in snapshot_alert_candidates(snapshot):
        key = item["alert_key"]
        seen.add(key)
        row = rows_by_key.get(key)
        if row is None:
            row = FleetAlert(
                branch_id=branch_id,
                vehicle_id=vehicle_id,
                alert_key=key,
                severity=item["severity"],
                label=item["label"],
                detail=item["detail"],
                source_type=item["source_type"],
                source_id=item["source_id"],
                fingerprint=item["fingerprint"],
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(row)
            db.flush()
            notify.append(row)
            continue

        changed = row.fingerprint != item["fingerprint"] or row.resolved_at is not None
        if row.resolved_at is not None:
            row.first_seen_at = now
        row.severity = item["severity"]
        row.label = item["label"]
        row.detail = item["detail"]
        row.source_type = item["source_type"]
        row.source_id = item["source_id"]
        row.fingerprint = item["fingerprint"]
        row.last_seen_at = now
        row.resolved_at = None
        if changed or row.last_notified_at is None:
            notify.append(row)

    for key, row in rows_by_key.items():
        if key not in seen and row.resolved_at is None:
            row.resolved_at = now
            row.last_seen_at = now

    return notify
