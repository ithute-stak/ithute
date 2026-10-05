from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.security import hash_token
from app.db.session import get_db
from app.models import HardwareTelemetrySnapshot, InfrastructureServer, InfrastructureServerAgent, User
from app.services.hardware_prediction import MetricPoint, predict_hardware_drift

router = APIRouter(prefix="/hardware-intelligence", tags=["hardware-intelligence"])

MAX_CLOCK_SKEW_SECONDS = 300
RETENTION_DAYS = 30


class HardwareEnvelope(BaseModel):
    envelope_version: int = Field(ge=1, le=1)
    algorithm: str = Field(pattern=r"^HMAC-SHA256$")
    agent_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    issued_at_unix: int = Field(ge=0)
    nonce: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    payload: dict[str, Any]
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


def _agent_from_token(db: Session, token: str | None) -> tuple[str, InfrastructureServerAgent, InfrastructureServer]:
    raw = (token or "").strip()
    if not raw or not raw.startswith("ith_srv_"):
        raise HTTPException(status_code=401, detail="Infrastructure server agent credential required")
    agent = db.scalar(select(InfrastructureServerAgent).where(InfrastructureServerAgent.token_hash == hash_token(raw)))
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid infrastructure server agent credential")
    server = db.get(InfrastructureServer, agent.server_id)
    if server is None or server.status == "disabled":
        raise HTTPException(status_code=403, detail="Infrastructure server is unavailable")
    return raw, agent, server


def _go_json(value: Any) -> bytes:
    # Go encoding/json emits UTF-8 while escaping HTML-sensitive code points.
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text = (
        text.replace("&", r"\u0026")
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace(" ", r"\u2028")
        .replace(" ", r"\u2029")
    )
    return text.encode("utf-8")


def _unsigned_envelope(payload: HardwareEnvelope) -> dict[str, Any]:
    return {
        "envelope_version": payload.envelope_version,
        "algorithm": payload.algorithm,
        "agent_id": payload.agent_id,
        "issued_at_unix": payload.issued_at_unix,
        "nonce": payload.nonce,
        "payload": payload.payload,
    }


def _verify_signature(payload: HardwareEnvelope, key: str) -> bool:
    expected = hmac.new(
        key.encode("utf-8"),
        _go_json(_unsigned_envelope(payload)),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, payload.signature)


def _number(container: dict[str, Any], key: str) -> float | None:
    raw = container.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if value != value or value in {float("inf"), float("-inf")}:
        return None
    return value


def _validate_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise HTTPException(status_code=422, detail="Unsupported hardware telemetry schema version")

    memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else {}
    total = _number(memory, "total_kb")
    available = _number(memory, "available_kb")
    if total is None or total <= 0 or available is None or available < 0 or available > total:
        raise HTTPException(status_code=422, detail="Invalid memory telemetry")

    thermal = payload.get("thermal") if isinstance(payload.get("thermal"), dict) else {}
    zones = _number(thermal, "zones_seen")
    temp = _number(thermal, "max_celsius")
    if zones is None or zones < 0 or zones > 4096:
        raise HTTPException(status_code=422, detail="Invalid thermal telemetry")
    if zones > 0 and (temp is None or temp < -100 or temp > 250):
        raise HTTPException(status_code=422, detail="Invalid thermal temperature")

    pressure = payload.get("pressure") if isinstance(payload.get("pressure"), dict) else {}
    for key in ("cpu_avg10", "memory_avg10", "io_avg10"):
        value = _number(pressure, key)
        if value is not None and value != -1 and not 0 <= value <= 100:
            raise HTTPException(status_code=422, detail=f"Invalid {key}")

    filesystem = payload.get("filesystem") if isinstance(payload.get("filesystem"), dict) else {}
    fs_total = _number(filesystem, "root_total_bytes")
    fs_available = _number(filesystem, "root_available_bytes")
    if fs_total is not None and fs_available is not None:
        if fs_total < 0 or fs_available < 0 or fs_available > fs_total:
            raise HTTPException(status_code=422, detail="Invalid filesystem telemetry")

    devices = payload.get("storage_devices")
    if devices is not None and (not isinstance(devices, list) or len(devices) > 64):
        raise HTTPException(status_code=422, detail="Invalid storage telemetry")



def _prediction_point_from_health(health: dict[str, Any]) -> MetricPoint:
    return MetricPoint(
        temperature_celsius=health.get("temperature_celsius"),
        memory_pressure_avg10=health.get("memory_pressure_avg10"),
        io_pressure_avg10=health.get("io_pressure_avg10"),
        filesystem_used_percent=health.get("filesystem_used_percent"),
    )


def _prediction_for_server(db: Session, server_id, current_health: dict[str, Any]) -> dict[str, Any]:
    rows = db.scalars(
        select(HardwareTelemetrySnapshot)
        .where(HardwareTelemetrySnapshot.server_id == server_id)
        .order_by(HardwareTelemetrySnapshot.created_at.desc())
        .limit(96)
    ).all()
    history = [
        MetricPoint(
            temperature_celsius=row.temperature_celsius,
            memory_pressure_avg10=row.memory_pressure_avg10,
            io_pressure_avg10=row.io_pressure_avg10,
            filesystem_used_percent=row.filesystem_used_percent,
        )
        for row in reversed(rows)
    ]
    return predict_hardware_drift(history, _prediction_point_from_health(current_health))



def _health(payload: dict[str, Any]) -> dict[str, Any]:
    score = 100
    evidence: list[str] = []
    critical = False

    thermal = payload.get("thermal") if isinstance(payload.get("thermal"), dict) else {}
    temperature = _number(thermal, "max_celsius")
    if temperature is not None and (_number(thermal, "zones_seen") or 0) > 0:
        if temperature >= 85:
            score -= 35
            critical = True
            evidence.append(f"host temperature {temperature:.1f}C")
        elif temperature >= 75:
            score -= 20
            evidence.append(f"host temperature {temperature:.1f}C")
        elif temperature >= 65:
            score -= 8
            evidence.append(f"host temperature {temperature:.1f}C")

    pressure = payload.get("pressure") if isinstance(payload.get("pressure"), dict) else {}
    memory_pressure = _number(pressure, "memory_avg10")
    io_pressure = _number(pressure, "io_avg10")
    for label, value in (("memory pressure", memory_pressure), ("I/O pressure", io_pressure)):
        if value is None or value < 0:
            continue
        if value >= 30:
            score -= 25
            evidence.append(f"{label} avg10 {value:.1f}%")
        elif value >= 15:
            score -= 12
            evidence.append(f"{label} avg10 {value:.1f}%")
        elif value >= 5:
            score -= 5
            evidence.append(f"{label} avg10 {value:.1f}%")

    filesystem = payload.get("filesystem") if isinstance(payload.get("filesystem"), dict) else {}
    fs_total = _number(filesystem, "root_total_bytes")
    fs_available = _number(filesystem, "root_available_bytes")
    fs_used_percent = None
    if fs_total and fs_total > 0 and fs_available is not None:
        fs_used_percent = max(0.0, min(100.0, ((fs_total - fs_available) / fs_total) * 100))
        if fs_used_percent >= 97:
            score -= 30
            critical = True
            evidence.append(f"root filesystem {fs_used_percent:.1f}% used")
        elif fs_used_percent >= 90:
            score -= 15
            evidence.append(f"root filesystem {fs_used_percent:.1f}% used")
        elif fs_used_percent >= 80:
            score -= 6
            evidence.append(f"root filesystem {fs_used_percent:.1f}% used")

    storage_warnings = 0
    devices = payload.get("storage_devices") if isinstance(payload.get("storage_devices"), list) else []
    for item in devices[:64]:
        if not isinstance(item, dict):
            continue
        failed = item.get("health_passed") is False
        critical_warning = _number(item, "critical_warning") or 0
        media_errors = _number(item, "media_errors") or 0
        percentage_used = _number(item, "percentage_used")
        device_temp = _number(item, "temperature_celsius")

        if failed or critical_warning > 0:
            storage_warnings += 1
            score -= 35
            critical = True
            evidence.append(f"{item.get('device') or 'storage'} reports critical SMART/NVMe health")
        elif media_errors > 0:
            storage_warnings += 1
            score -= 18
            evidence.append(f"{item.get('device') or 'storage'} media errors={int(media_errors)}")
        if percentage_used is not None and percentage_used >= 95:
            storage_warnings += 1
            score -= 15
            evidence.append(f"{item.get('device') or 'storage'} {percentage_used:.0f}% endurance used")
        if device_temp is not None and device_temp >= 75:
            storage_warnings += 1
            score -= 10
            evidence.append(f"{item.get('device') or 'storage'} temperature {device_temp:.1f}C")

    score = max(0, min(100, score))
    status = "critical" if critical or score < 50 else "warning" if score < 80 else "healthy"
    return {
        "score": score,
        "status": status,
        "evidence": evidence[:20],
        "temperature_celsius": temperature,
        "memory_pressure_avg10": memory_pressure,
        "io_pressure_avg10": io_pressure,
        "filesystem_used_percent": fs_used_percent,
        "storage_warning_count": storage_warnings,
    }


@router.post("/telemetry", status_code=202)
def ingest_hardware_telemetry(
    payload: HardwareEnvelope,
    x_ithute_server_agent: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    raw_token, agent, server = _agent_from_token(db, x_ithute_server_agent)
    if payload.agent_id != str(server.id):
        raise HTTPException(status_code=403, detail="Hardware agent identity does not match infrastructure server")
    if not _verify_signature(payload, raw_token):
        raise HTTPException(status_code=401, detail="Invalid hardware telemetry signature")

    now = datetime.now(timezone.utc)
    issued_at = datetime.fromtimestamp(payload.issued_at_unix, tz=timezone.utc)
    if abs((now - issued_at).total_seconds()) > MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=409, detail="Hardware telemetry timestamp is outside the accepted window")

    _validate_payload(payload.payload)
    health = _health(payload.payload)
    prediction = _prediction_for_server(db, server.id, health)

    row = HardwareTelemetrySnapshot(
        server_id=server.id,
        agent_id=payload.agent_id,
        issued_at=issued_at,
        nonce=payload.nonce,
        signature=payload.signature,
        payload_json=json.dumps(payload.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        health_score=health["score"],
        health_status=health["status"],
        temperature_celsius=health["temperature_celsius"],
        memory_pressure_avg10=health["memory_pressure_avg10"],
        io_pressure_avg10=health["io_pressure_avg10"],
        filesystem_used_percent=health["filesystem_used_percent"],
        storage_warning_count=health["storage_warning_count"],
        predictive_risk_score=prediction["risk_score"],
        predictive_state=prediction["state"],
        predictive_confidence=prediction["confidence"],
        predictive_evidence_json=json.dumps(prediction["evidence"], ensure_ascii=False, separators=(",", ":")),
    )
    db.add(row)
    agent.last_seen_at = now
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Hardware telemetry nonce has already been used") from exc

    db.execute(
        delete(HardwareTelemetrySnapshot).where(
            HardwareTelemetrySnapshot.server_id == server.id,
            HardwareTelemetrySnapshot.created_at < now - timedelta(days=RETENTION_DAYS),
        )
    )
    db.commit()
    return {
        "accepted": True,
        "server_id": str(server.id),
        "health": {
            "score": health["score"],
            "status": health["status"],
            "evidence": health["evidence"],
        },
        "prediction": prediction,
    }


@router.get("/servers/{server_id}/latest")
def latest_hardware_health(
    server_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    try:
        from uuid import UUID
        parsed = UUID(server_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid infrastructure server id") from exc

    row = db.scalar(
        select(HardwareTelemetrySnapshot)
        .where(HardwareTelemetrySnapshot.server_id == parsed)
        .order_by(HardwareTelemetrySnapshot.created_at.desc())
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No hardware telemetry has been received for this server")
    return {
        "server_id": str(row.server_id),
        "agent_id": row.agent_id,
        "health_score": row.health_score,
        "health_status": row.health_status,
        "temperature_celsius": row.temperature_celsius,
        "memory_pressure_avg10": row.memory_pressure_avg10,
        "io_pressure_avg10": row.io_pressure_avg10,
        "filesystem_used_percent": row.filesystem_used_percent,
        "storage_warning_count": row.storage_warning_count,
        "prediction": {
            "risk_score": row.predictive_risk_score,
            "state": row.predictive_state or "learning",
            "confidence": row.predictive_confidence,
            "evidence": json.loads(row.predictive_evidence_json or "[]"),
        },
        "sampled_at": row.issued_at.isoformat(),
        "received_at": row.created_at.isoformat() if row.created_at else None,
        "payload": json.loads(row.payload_json),
    }


@router.get("/fleet")
def hardware_fleet_health(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    servers = db.scalars(
        select(InfrastructureServer)
        .where(InfrastructureServer.status != "disabled")
        .order_by(InfrastructureServer.name.asc())
    ).all()

    items: list[dict[str, Any]] = []
    counts = {"healthy": 0, "warning": 0, "critical": 0, "offline": 0, "unknown": 0}
    predictive_counts = {"learning": 0, "stable": 0, "watch": 0, "elevated": 0, "high": 0}
    now = datetime.now(timezone.utc)
    for server in servers:
        agent = db.get(InfrastructureServerAgent, server.id)
        latest = db.scalar(
            select(HardwareTelemetrySnapshot)
            .where(HardwareTelemetrySnapshot.server_id == server.id)
            .order_by(HardwareTelemetrySnapshot.created_at.desc())
        )

        online = bool(
            agent
            and agent.last_seen_at
            and now - (agent.last_seen_at if agent.last_seen_at.tzinfo else agent.last_seen_at.replace(tzinfo=timezone.utc))
            <= timedelta(minutes=5)
        )
        if not online:
            status = "offline"
            score = 0
        elif latest is None:
            status = "unknown"
            score = None
        else:
            status = latest.health_status
            score = latest.health_score
        counts[status] = counts.get(status, 0) + 1
        predictive_state = (latest.predictive_state or "learning") if latest else "learning"
        predictive_counts[predictive_state] = predictive_counts.get(predictive_state, 0) + 1

        evidence: list[str] = []
        payload: dict[str, Any] = {}
        if latest:
            try:
                payload = json.loads(latest.payload_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            evidence = _health(payload)["evidence"]

        items.append({
            "server_id": str(server.id),
            "name": server.name,
            "hostname": server.hostname,
            "provider": server.provider,
            "region": server.region,
            "roles": json.loads(server.roles_json or "[]"),
            "status": status,
            "health_score": score,
            "online": online,
            "last_seen_at": agent.last_seen_at.isoformat() if agent and agent.last_seen_at else None,
            "temperature_celsius": latest.temperature_celsius if latest else None,
            "memory_pressure_avg10": latest.memory_pressure_avg10 if latest else None,
            "io_pressure_avg10": latest.io_pressure_avg10 if latest else None,
            "filesystem_used_percent": latest.filesystem_used_percent if latest else None,
            "storage_warning_count": latest.storage_warning_count if latest else 0,
            "predictive_risk_score": latest.predictive_risk_score if latest else None,
            "predictive_state": predictive_state,
            "predictive_confidence": latest.predictive_confidence if latest else None,
            "predictive_evidence": json.loads(latest.predictive_evidence_json or "[]") if latest else [],
            "evidence": evidence,
            "sampled_at": latest.issued_at.isoformat() if latest else None,
        })

    return {
        "generated_at": now.isoformat(),
        "counts": counts,
        "predictive_counts": predictive_counts,
        "total": len(items),
        "items": items,
    }


@router.get("/servers/{server_id}/history")
def hardware_health_history(
    server_id: str,
    hours: int = 24,
    limit: int = 288,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    try:
        from uuid import UUID
        parsed = UUID(server_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid infrastructure server id") from exc

    server = db.get(InfrastructureServer, parsed)
    if server is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")

    safe_hours = max(1, min(hours, 24 * 30))
    safe_limit = max(1, min(limit, 2000))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=safe_hours)
    rows = db.scalars(
        select(HardwareTelemetrySnapshot)
        .where(
            HardwareTelemetrySnapshot.server_id == parsed,
            HardwareTelemetrySnapshot.created_at >= cutoff,
        )
        .order_by(HardwareTelemetrySnapshot.created_at.asc())
        .limit(safe_limit)
    ).all()

    return {
        "server_id": str(server.id),
        "name": server.name,
        "hostname": server.hostname,
        "hours": safe_hours,
        "items": [
            {
                "sampled_at": row.issued_at.isoformat(),
                "received_at": row.created_at.isoformat() if row.created_at else None,
                "health_score": row.health_score,
                "health_status": row.health_status,
                "temperature_celsius": row.temperature_celsius,
                "memory_pressure_avg10": row.memory_pressure_avg10,
                "io_pressure_avg10": row.io_pressure_avg10,
                "filesystem_used_percent": row.filesystem_used_percent,
                "storage_warning_count": row.storage_warning_count,
                "predictive_risk_score": row.predictive_risk_score,
                "predictive_state": row.predictive_state or "learning",
                "predictive_confidence": row.predictive_confidence,
            }
            for row in rows
        ],
    }
