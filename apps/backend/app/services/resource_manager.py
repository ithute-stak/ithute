from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    HostingDatabase,
    HostingFailoverAttempt,
    HostingNode,
    HostingProject,
    HostingResourceReservation,
    InfrastructureServer,
    InfrastructureServerAgent,
)


ACTIVE_PROJECT_EXCLUSIONS = {"suspended"}
ACTIVE_RESERVATION_STATUS = "active"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def expire_reservations(db: Session, *, now: datetime | None = None, node_id: UUID | None = None) -> int:
    now = now or _utcnow()
    query = select(HostingResourceReservation).where(
        HostingResourceReservation.status == ACTIVE_RESERVATION_STATUS,
        HostingResourceReservation.expires_at <= now,
    )
    if node_id is not None:
        query = query.where(HostingResourceReservation.node_id == node_id)
    rows = db.scalars(query).all()
    for row in rows:
        row.status = "expired"
        row.released_at = now
    return len(rows)


def node_commitments(db: Session, node_id: UUID, *, now: datetime | None = None) -> dict:
    now = now or _utcnow()
    expire_reservations(db, now=now, node_id=node_id)

    project_row = db.execute(
        select(
            func.coalesce(func.sum(HostingProject.cpu_millicores), 0),
            func.coalesce(func.sum(HostingProject.memory_mb), 0),
            func.coalesce(func.sum(HostingProject.storage_mb), 0),
            func.count(HostingProject.id),
        ).where(
            HostingProject.node_id == node_id,
            HostingProject.status.not_in(ACTIVE_PROJECT_EXCLUSIONS),
        )
    ).one()
    database_storage = int(
        db.scalar(
            select(func.coalesce(func.sum(HostingDatabase.storage_mb), 0)).where(
                HostingDatabase.node_id == node_id,
                HostingDatabase.status != "deleting",
            )
        )
        or 0
    )

    reservation_row = db.execute(
        select(
            func.coalesce(func.sum(HostingResourceReservation.cpu_millicores), 0),
            func.coalesce(func.sum(HostingResourceReservation.memory_mb), 0),
            func.coalesce(func.sum(HostingResourceReservation.storage_mb), 0),
        ).where(
            HostingResourceReservation.node_id == node_id,
            HostingResourceReservation.status == ACTIVE_RESERVATION_STATUS,
            HostingResourceReservation.expires_at > now,
        )
    ).one()

    legacy_failover = db.execute(
        select(
            func.coalesce(func.sum(HostingProject.cpu_millicores), 0),
            func.coalesce(func.sum(HostingProject.memory_mb), 0),
            func.coalesce(func.sum(HostingProject.storage_mb), 0),
            func.count(HostingProject.id),
        )
        .join(HostingFailoverAttempt, HostingFailoverAttempt.project_id == HostingProject.id)
        .where(
            HostingFailoverAttempt.target_node_id == node_id,
            HostingFailoverAttempt.status.in_(["pending", "deploying", "edge_pending"]),
            HostingProject.node_id != node_id,
        )
    ).one()

    allocated = {
        "cpu_millicores": int(project_row[0] or 0),
        "memory_mb": int(project_row[1] or 0),
        "storage_mb": int(project_row[2] or 0) + database_storage,
    }
    reserved = {
        "cpu_millicores": int(reservation_row[0] or 0) + int(legacy_failover[0] or 0),
        "memory_mb": int(reservation_row[1] or 0) + int(legacy_failover[1] or 0),
        "storage_mb": int(reservation_row[2] or 0) + int(legacy_failover[2] or 0),
    }
    return {
        "allocated": allocated,
        "reserved": reserved,
        "details": {
            "app_storage_mb": int(project_row[2] or 0),
            "database_storage_mb": database_storage,
            "project_count": int(project_row[3] or 0),
            "explicit_reserved_cpu_millicores": int(reservation_row[0] or 0),
            "explicit_reserved_memory_mb": int(reservation_row[1] or 0),
            "explicit_reserved_storage_mb": int(reservation_row[2] or 0),
            "failover_reserved_cpu_millicores": int(legacy_failover[0] or 0),
            "failover_reserved_memory_mb": int(legacy_failover[1] or 0),
            "failover_reserved_storage_mb": int(legacy_failover[2] or 0),
            "failover_reserved_projects": int(legacy_failover[3] or 0),
        },
    }


def _live_usage(db: Session, node_id: UUID) -> dict:
    server = db.scalar(select(InfrastructureServer).where(InfrastructureServer.hosting_node_id == node_id))
    agent = db.get(InfrastructureServerAgent, server.id) if server else None
    try:
        telemetry = json.loads(agent.telemetry_json or "{}") if agent else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        telemetry = {}
    if not isinstance(telemetry, dict):
        telemetry = {}

    cpu = telemetry.get("cpu") if isinstance(telemetry.get("cpu"), dict) else {}
    memory = telemetry.get("memory") if isinstance(telemetry.get("memory"), dict) else {}
    disks = telemetry.get("disks") if isinstance(telemetry.get("disks"), list) else []

    try:
        cpu_percent = max(0.0, min(float(cpu.get("used_percent") or 0.0), 100.0))
    except (TypeError, ValueError):
        cpu_percent = 0.0

    memory_used_bytes = 0
    try:
        memory_used_bytes = max(0, int(memory.get("used_bytes") or 0))
    except (TypeError, ValueError, OverflowError):
        pass

    storage_used_bytes = 0
    storage_total_bytes = 0
    for disk in disks[:128]:
        if not isinstance(disk, dict):
            continue
        try:
            storage_used_bytes += max(0, int(disk.get("used_bytes") or 0))
            storage_total_bytes += max(0, int(disk.get("total_bytes") or 0))
        except (TypeError, ValueError, OverflowError):
            continue

    return {
        "cpu_used_percent": round(cpu_percent, 2),
        "memory_used_bytes": memory_used_bytes,
        "storage_used_bytes": storage_used_bytes,
        "storage_total_bytes": storage_total_bytes,
        "telemetry_available": agent is not None,
    }


def node_resource_snapshot(db: Session, node: HostingNode, *, now: datetime | None = None) -> dict:
    now = now or _utcnow()
    capacity = {
        "cpu_millicores": int(node.allocatable_cpu_millicores),
        "memory_mb": int(node.allocatable_memory_mb),
        "storage_mb": int(node.allocatable_storage_mb),
    }
    commitments = node_commitments(db, node.id, now=now)
    allocated = commitments["allocated"]
    reserved = commitments["reserved"]
    available = {
        key: max(0, capacity[key] - allocated[key] - reserved[key])
        for key in capacity
    }
    committed = {
        key: allocated[key] + reserved[key]
        for key in capacity
    }
    overcommitted = {
        key: committed[key] > capacity[key]
        for key in capacity
    }
    return {
        "node_id": str(node.id),
        "node_name": node.name,
        "capacity": capacity,
        "allocated": allocated,
        "reserved": reserved,
        "committed": committed,
        "available": available,
        "overcommitted": overcommitted,
        "used": _live_usage(db, node.id),
        "details": commitments["details"],
        "as_of": now.isoformat(),
    }


def reserve_capacity(
    db: Session,
    *,
    node_id: UUID,
    cpu_millicores: int,
    memory_mb: int,
    storage_mb: int,
    expires_at: datetime,
    created_by_user_id: UUID,
    project_id: UUID | None = None,
    purpose: str = "placement",
) -> HostingResourceReservation:
    now = _utcnow()
    node = db.scalar(
        select(HostingNode)
        .where(HostingNode.id == node_id)
        .with_for_update()
    )
    if node is None:
        raise ValueError("hosting node not found")
    if node.status != "active" or not node.accepts_new_projects:
        raise ValueError("hosting node is not accepting new projects")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise ValueError("reservation expiry must be in the future")

    request = {
        "cpu_millicores": max(0, int(cpu_millicores)),
        "memory_mb": max(0, int(memory_mb)),
        "storage_mb": max(0, int(storage_mb)),
    }
    if not any(request.values()):
        raise ValueError("reservation must request at least one resource")

    if project_id is not None:
        existing = db.scalar(
            select(HostingResourceReservation)
            .where(
                HostingResourceReservation.project_id == project_id,
                HostingResourceReservation.status == ACTIVE_RESERVATION_STATUS,
                HostingResourceReservation.expires_at > now,
            )
            .with_for_update()
        )
        if existing is not None:
            raise ValueError("project already has an active resource reservation")

    snapshot = node_resource_snapshot(db, node, now=now)
    insufficient = [
        key for key, value in request.items()
        if value > snapshot["available"][key]
    ]
    if insufficient:
        raise ValueError("insufficient available capacity: " + ", ".join(sorted(insufficient)))

    reservation = HostingResourceReservation(
        node_id=node.id,
        project_id=project_id,
        purpose=purpose.strip()[:80] or "placement",
        cpu_millicores=request["cpu_millicores"],
        memory_mb=request["memory_mb"],
        storage_mb=request["storage_mb"],
        status=ACTIVE_RESERVATION_STATUS,
        expires_at=expires_at,
        created_by_user_id=created_by_user_id,
    )
    db.add(reservation)
    db.flush()
    return reservation


def release_reservation(
    db: Session,
    reservation_id: UUID,
    *,
    now: datetime | None = None,
) -> HostingResourceReservation | None:
    now = now or _utcnow()
    reservation = db.scalar(
        select(HostingResourceReservation)
        .where(HostingResourceReservation.id == reservation_id)
        .with_for_update()
    )
    if reservation is None:
        return None
    if reservation.status == ACTIVE_RESERVATION_STATUS:
        reservation.status = "released"
        reservation.released_at = now
    return reservation
