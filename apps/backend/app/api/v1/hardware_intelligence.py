from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.security import hash_token
from app.db.session import get_db
from app.models import HardwareAlertAcknowledgement, HardwareFailureLabel, HardwareIncident, HardwareIncidentDelivery, HardwareMaintenanceTask, HardwareMaintenanceWindow, HardwareTelemetrySnapshot, InfrastructureServer, InfrastructureServerAgent, Notification, User
from app.services.engine_runtime import hardware_workflow_plan
from app.services.hardware_prediction import MetricPoint, derive_rate_features, predict_hardware_drift
from app.services.hardware_remediation_verification import verify_remediation
from app.services.hardware_supervised_learning import supervised_training_readiness

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


class MaintenanceWindowCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=3, max_length=500)
    suppress_notifications: bool = True


class AlertAcknowledgementCreate(BaseModel):
    note: str = Field(default="", max_length=1000)


class MaintenanceTaskUpdate(BaseModel):
    status: str = Field(pattern=r"^(in_progress|completed|cancelled)$")
    note: str = Field(default="", max_length=1000)
    remediation_action: str = Field(default="", max_length=128)
    outcome: str = Field(default="", pattern=r"^(|resolved|improved|no_change|worsened)$")


class FailureLabelUpsert(BaseModel):
    label: str = Field(pattern=r"^(confirmed_failure|confirmed_degradation|false_positive|inconclusive)$")
    component: str = Field(
        default="unknown",
        pattern=r"^(unknown|cpu|memory|storage|thermal|network|power|motherboard|other)$",
    )
    confidence: float = Field(ge=0.5, le=1.0)
    evidence: str = Field(min_length=3, max_length=2000)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _window_active_at(window: HardwareMaintenanceWindow, at: datetime) -> bool:
    return (
        window.cancelled_at is None
        and _utc(window.starts_at) <= at
        and _utc(window.ends_at) > at
    )


def _active_maintenance(db: Session, server_id, at: datetime | None = None) -> HardwareMaintenanceWindow | None:
    now = at or datetime.now(timezone.utc)
    rows = db.scalars(
        select(HardwareMaintenanceWindow)
        .where(
            HardwareMaintenanceWindow.server_id == server_id,
            HardwareMaintenanceWindow.cancelled_at.is_(None),
            HardwareMaintenanceWindow.starts_at <= now,
            HardwareMaintenanceWindow.ends_at > now,
        )
        .order_by(HardwareMaintenanceWindow.ends_at.asc())
    ).all()
    return rows[0] if rows else None


def _ack_for_snapshot(db: Session, snapshot_id) -> HardwareAlertAcknowledgement | None:
    if snapshot_id is None:
        return None
    return db.scalar(
        select(HardwareAlertAcknowledgement).where(
            HardwareAlertAcknowledgement.snapshot_id == snapshot_id
        )
    )

def _active_hardware_incident(db: Session, server_id) -> HardwareIncident | None:
    return db.scalar(
        select(HardwareIncident)
        .where(
            HardwareIncident.server_id == server_id,
            HardwareIncident.status == "open",
        )
        .order_by(HardwareIncident.opened_at.desc())
        .limit(1)
    )


def _hardware_incident_summary(server: InfrastructureServer, health: dict[str, Any], prediction: dict[str, Any]) -> tuple[str, str, str]:
    predictive_state = str(prediction.get("state") or "learning").strip().lower()
    risk_score = prediction.get("risk_score")
    critical = health.get("status") == "critical"
    severity = "critical" if critical else "high"
    if critical:
        title = f"Critical hardware health on {server.name}"
        evidence = list(health.get("evidence") or [])
    else:
        title = f"High predicted hardware failure risk on {server.name}"
        evidence = list(prediction.get("evidence") or [])
    risk_text = f" Predictive risk is {risk_score}/100 ({predictive_state})." if risk_score is not None else ""
    evidence_text = f" Evidence: {'; '.join(str(item) for item in evidence[:5])}." if evidence else ""
    return severity, title, f"{title}.{risk_text}{evidence_text}"


def _queue_hardware_incident_delivery(
    db: Session,
    *,
    incident: HardwareIncident,
    owner: User,
    channel: str,
) -> None:
    existing = db.scalar(
        select(HardwareIncidentDelivery).where(
            HardwareIncidentDelivery.incident_id == incident.id,
            HardwareIncidentDelivery.recipient_user_id == owner.id,
            HardwareIncidentDelivery.channel == channel,
        )
    )
    if existing is None:
        db.add(
            HardwareIncidentDelivery(
                incident_id=incident.id,
                recipient_user_id=owner.id,
                channel=channel,
                status="queued",
            )
        )


def _queue_hardware_incident_notifications(
    db: Session,
    *,
    incident: HardwareIncident,
    server: InfrastructureServer,
    severity: str,
    title: str,
    summary: str,
) -> None:
    owners = db.scalars(
        select(User).where(User.is_platform_owner.is_(True), User.is_active.is_(True))
    ).all()
    for owner in owners:
        existing_notice = db.scalar(
            select(Notification).where(
                Notification.user_id == owner.id,
                Notification.category == "hardware_intelligence",
                Notification.action_url == f"/system-owner/hardware-intelligence?server={server.id}&incident={incident.id}",
                Notification.title == title,
            )
        )
        if existing_notice is None:
            db.add(
                Notification(
                    tenant_id=None,
                    user_id=owner.id,
                    category="hardware_intelligence",
                    severity=severity,
                    title=title,
                    message=summary,
                    action_url=f"/system-owner/hardware-intelligence?server={server.id}&incident={incident.id}",
                )
            )
        _queue_hardware_incident_delivery(db, incident=incident, owner=owner, channel="email")
        _queue_hardware_incident_delivery(db, incident=incident, owner=owner, channel="push")


def _ensure_hardware_maintenance_task(
    db: Session,
    *,
    incident: HardwareIncident,
    server: InfrastructureServer,
    workflow_plan: dict[str, Any],
    title: str,
    summary: str,
    severity: str,
) -> HardwareMaintenanceTask | None:
    actions = workflow_plan.get("actions") if isinstance(workflow_plan.get("actions"), list) else []
    recommendations = workflow_plan.get("recommendations") if isinstance(workflow_plan.get("recommendations"), list) else []
    ranked = workflow_plan.get("ranked_recommendations") if isinstance(workflow_plan.get("ranked_recommendations"), list) else []
    if "create_maintenance_task" not in actions:
        return None
    recommendation_lines: list[str] = []
    for item in ranked[:10]:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").replace("_", " ")
        score = item.get("priority_score")
        confidence = item.get("confidence_percent")
        urgency = str(item.get("urgency") or "")
        impact = str(item.get("expected_impact") or "")
        recommendation_lines.append(
            f"- [{score}/100 · {urgency} · confidence {confidence}%] {action}"
            + (f" — {impact}" if impact else "")
        )
    if not recommendation_lines:
        recommendation_lines = [f"- {str(item).replace('_', ' ')}" for item in recommendations[:10]]
    recommendation_text = "\n".join(recommendation_lines)
    task_description = summary if not recommendation_text else f"{summary}\n\nRecommended remediation:\n{recommendation_text}"
    existing = db.scalar(
        select(HardwareMaintenanceTask).where(HardwareMaintenanceTask.incident_id == incident.id)
    )
    if existing is not None:
        existing.priority = severity
        existing.title = title
        existing.description = task_description
        if existing.remediation_baseline_snapshot_id is None:
            existing.remediation_baseline_snapshot_id = incident.latest_snapshot_id
        return existing

    task = HardwareMaintenanceTask(
        incident_id=incident.id,
        server_id=server.id,
        priority=severity,
        status="open",
        title=title,
        description=task_description,
        remediation_baseline_snapshot_id=incident.latest_snapshot_id,
    )
    db.add(task)
    return task


def _remediation_outcome_stats(db: Session) -> dict[str, dict[str, float | int]]:
    rows = db.execute(
        select(
            HardwareMaintenanceTask.remediation_action,
            HardwareMaintenanceTask.measured_outcome,
            HardwareMaintenanceTask.verification_confidence,
        )
        .where(
            HardwareMaintenanceTask.status == "completed",
            HardwareMaintenanceTask.remediation_action != "",
            HardwareMaintenanceTask.measured_outcome.in_(["resolved", "improved", "no_change", "worsened"]),
            HardwareMaintenanceTask.verification_confidence >= 0.5,
        )
    ).all()
    totals: dict[str, dict[str, float | int]] = {}
    impact = {"resolved": 1.0, "improved": 0.5, "no_change": 0.0, "worsened": -1.0}
    positive = {"resolved": 1.0, "improved": 0.5, "no_change": 0.0, "worsened": 0.0}
    for action, measured_outcome, verification_confidence in rows:
        key = str(action or "").strip()
        outcome = str(measured_outcome or "").strip()
        if not key or outcome not in impact:
            continue
        weight = max(0.25, min(1.0, float(verification_confidence or 0.0)))
        bucket = totals.setdefault(key, {"samples": 0, "weight_sum": 0.0, "impact_sum": 0.0, "positive_sum": 0.0})
        bucket["samples"] = int(bucket["samples"]) + 1
        bucket["weight_sum"] = float(bucket["weight_sum"]) + weight
        bucket["impact_sum"] = float(bucket["impact_sum"]) + impact[outcome] * weight
        bucket["positive_sum"] = float(bucket["positive_sum"]) + positive[outcome] * weight
    return {
        action: {
            "samples": int(values["samples"]),
            "verified_samples": int(values["samples"]),
            "mean_impact": round(float(values["impact_sum"]) / max(0.25, float(values["weight_sum"])), 3),
            "success_rate": round(float(values["positive_sum"]) / max(0.25, float(values["weight_sum"])), 3),
        }
        for action, values in totals.items()
    }

def _apply_remediation_learning(workflow_plan: dict[str, Any], stats: dict[str, dict[str, float | int]]) -> dict[str, Any]:
    ranked = workflow_plan.get("ranked_recommendations")
    if not isinstance(ranked, list) or not ranked:
        return workflow_plan
    adjusted: list[dict[str, Any]] = []
    for raw in ranked:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        action = str(item.get("action") or "").strip()
        learned = stats.get(action)
        if learned and int(learned.get("samples") or 0) >= 3:
            mean_impact = max(-1.0, min(1.0, float(learned.get("mean_impact") or 0.0)))
            samples = int(learned.get("samples") or 0)
            priority = int(item.get("priority_score") or 0)
            confidence = int(item.get("confidence_percent") or 0)
            item["priority_score"] = max(0, min(100, priority + round(mean_impact * 8)))
            item["confidence_percent"] = max(0, min(100, confidence + round(mean_impact * 10)))
            item["learned_samples"] = samples
            item["learned_success_rate"] = round(float(learned.get("success_rate") or 0.0) * 100, 1)
            item["learning_adjustment"] = round(mean_impact * 8)
        adjusted.append(item)
    adjusted.sort(key=lambda item: int(item.get("priority_score") or 0), reverse=True)
    return {**workflow_plan, "ranked_recommendations": adjusted, "outcome_learning": {"eligible_actions": sum(1 for value in stats.values() if int(value.get("samples") or 0) >= 3)}}


def _snapshot_verification_payload(row: HardwareTelemetrySnapshot) -> dict[str, Any]:
    return {
        "health_score": row.health_score,
        "predictive_risk_score": row.predictive_risk_score,
        "temperature_celsius": row.temperature_celsius,
        "memory_pressure_avg10": row.memory_pressure_avg10,
        "io_pressure_avg10": row.io_pressure_avg10,
        "filesystem_used_percent": row.filesystem_used_percent,
        "storage_warning_count": row.storage_warning_count,
    }


def _verify_completed_remediation(
    db: Session,
    server_id,
    current_snapshot: HardwareTelemetrySnapshot,
    now: datetime,
) -> dict[str, Any] | None:
    task = db.scalar(
        select(HardwareMaintenanceTask)
        .where(
            HardwareMaintenanceTask.server_id == server_id,
            HardwareMaintenanceTask.status == "completed",
            HardwareMaintenanceTask.completed_at.is_not(None),
            HardwareMaintenanceTask.remediation_baseline_snapshot_id.is_not(None),
            HardwareMaintenanceTask.remediation_action != "",
            HardwareMaintenanceTask.verification_sample_count < 6,
        )
        .order_by(HardwareMaintenanceTask.completed_at.desc())
        .limit(1)
    )
    if task is None or task.completed_at is None:
        return None

    baseline = db.get(HardwareTelemetrySnapshot, task.remediation_baseline_snapshot_id)
    if baseline is None:
        return None

    completed_at = _utc(task.completed_at)
    post_rows = list(
        db.scalars(
            select(HardwareTelemetrySnapshot)
            .where(
                HardwareTelemetrySnapshot.server_id == server_id,
                HardwareTelemetrySnapshot.issued_at >= completed_at,
            )
            .order_by(HardwareTelemetrySnapshot.issued_at.desc())
            .limit(6)
        ).all()
    )
    post_rows.reverse()
    if current_snapshot.issued_at >= completed_at and all(row.id != current_snapshot.id for row in post_rows):
        post_rows.append(current_snapshot)
        post_rows = post_rows[-6:]

    result = verify_remediation(
        _snapshot_verification_payload(baseline),
        [_snapshot_verification_payload(row) for row in post_rows],
        task.remediation_action,
    )
    task.verification_sample_count = int(result.get("sample_count") or 0)
    task.verification_confidence = float(result.get("confidence") or 0.0)
    task.verification_evidence_json = json.dumps(result.get("evidence") or [], ensure_ascii=False, separators=(",", ":"))
    if result.get("ready"):
        task.measured_outcome = str(result.get("outcome") or "")
        task.remediation_verified_snapshot_id = current_snapshot.id
        task.verification_evaluated_at = now
    return result


def _reconcile_hardware_incident(
    db: Session,
    server: InfrastructureServer,
    snapshot: HardwareTelemetrySnapshot,
    health: dict[str, Any],
    prediction: dict[str, Any],
    maintenance: HardwareMaintenanceWindow | None,
    now: datetime,
) -> HardwareIncident | None:
    predictive_state = str(prediction.get("state") or "learning").strip().lower()
    active_risk = health.get("status") == "critical" or predictive_state == "high"
    incident = _active_hardware_incident(db, server.id)

    if not active_risk:
        if incident is not None:
            incident.status = "resolved"
            incident.resolved_at = now
            incident.last_seen_at = now
            incident.latest_snapshot_id = snapshot.id
        return incident

    severity, title, summary = _hardware_incident_summary(server, health, prediction)
    suppressed = bool(maintenance and maintenance.suppress_notifications)
    workflow_plan, workflow_engine = hardware_workflow_plan({
        "severity": severity,
        "health_status": str(health.get("status") or "unknown"),
        "predictive_state": predictive_state,
        "notification_suppressed": suppressed,
        "temperature_celsius": snapshot.temperature_celsius,
        "memory_pressure_avg10": snapshot.memory_pressure_avg10,
        "io_pressure_avg10": snapshot.io_pressure_avg10,
        "filesystem_used_percent": snapshot.filesystem_used_percent,
        "storage_warning_count": snapshot.storage_warning_count,
        "predictive_risk_score": snapshot.predictive_risk_score,
        "predictive_confidence": snapshot.predictive_confidence,
    })
    workflow_plan = {**workflow_plan, "engine": workflow_engine}
    workflow_plan = _apply_remediation_learning(workflow_plan, _remediation_outcome_stats(db))

    was_suppressed = bool(incident and incident.notification_suppressed)

    if incident is None:
        incident = HardwareIncident(
            server_id=server.id,
            latest_snapshot_id=snapshot.id,
            kind="hardware_risk",
            severity=severity,
            status="open",
            title=title,
            summary=summary,
            predictive_state=predictive_state,
            predictive_risk_score=prediction.get("risk_score"),
            health_status=str(health.get("status") or "unknown"),
            notification_suppressed=suppressed,
            workflow_plan_json=json.dumps(workflow_plan, sort_keys=True, separators=(",", ":")),
            opened_at=now,
            last_seen_at=now,
        )
        db.add(incident)
        db.flush()

        if not suppressed:
            _queue_hardware_incident_notifications(
                db,
                incident=incident,
                server=server,
                severity=severity,
                title=title,
                summary=summary,
            )
        _ensure_hardware_maintenance_task(
            db,
            incident=incident,
            server=server,
            workflow_plan=workflow_plan,
            title=title,
            summary=summary,
            severity=severity,
        )
    else:
        incident.latest_snapshot_id = snapshot.id
        incident.severity = severity
        incident.title = title
        incident.summary = summary
        incident.predictive_state = predictive_state
        incident.predictive_risk_score = prediction.get("risk_score")
        incident.health_status = str(health.get("status") or "unknown")
        incident.notification_suppressed = suppressed
        incident.workflow_plan_json = json.dumps(workflow_plan, sort_keys=True, separators=(",", ":"))
        incident.last_seen_at = now
        incident.resolved_at = None

        if was_suppressed and not suppressed:
            _queue_hardware_incident_notifications(
                db,
                incident=incident,
                server=server,
                severity=severity,
                title=title,
                summary=summary,
            )
        _ensure_hardware_maintenance_task(
            db,
            incident=incident,
            server=server,
            workflow_plan=workflow_plan,
            title=title,
            summary=summary,
            severity=severity,
        )

    return incident



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



def _safe_payload_json(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _prediction_point_from_health(
    health: dict[str, Any],
    previous_payload: dict[str, Any] | None = None,
    current_payload: dict[str, Any] | None = None,
) -> MetricPoint:
    rate = derive_rate_features(previous_payload, current_payload)
    return MetricPoint(
        temperature_celsius=health.get("temperature_celsius"),
        memory_pressure_avg10=health.get("memory_pressure_avg10"),
        io_pressure_avg10=health.get("io_pressure_avg10"),
        filesystem_used_percent=health.get("filesystem_used_percent"),
        cpu_iowait_percent=rate.get("cpu_iowait_percent"),
        cpu_steal_percent=rate.get("cpu_steal_percent"),
        block_io_ms_per_op=rate.get("block_io_ms_per_op"),
        block_weighted_ms_per_op=rate.get("block_weighted_ms_per_op"),
        media_error_delta=rate.get("media_error_delta"),
        network_error_delta=rate.get("network_error_delta"),
        tcp_retrans_delta=rate.get("tcp_retrans_delta"),
        ebpf_inflight_delta=rate.get("ebpf_inflight_delta"),
        ebpf_oom_delta=rate.get("ebpf_oom_delta"),
        ebpf_block_p50_ms=rate.get("ebpf_block_p50_ms"),
        ebpf_block_p95_ms=rate.get("ebpf_block_p95_ms"),
        ebpf_block_p99_ms=rate.get("ebpf_block_p99_ms"),
        ecc_corrected_delta=rate.get("ecc_corrected_delta"),
        ecc_uncorrected_delta=rate.get("ecc_uncorrected_delta"),
    )


def _prediction_for_server(
    db: Session,
    server_id,
    current_health: dict[str, Any],
    current_payload: dict[str, Any],
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(HardwareTelemetrySnapshot)
            .where(HardwareTelemetrySnapshot.server_id == server_id)
            .order_by(HardwareTelemetrySnapshot.created_at.desc())
            .limit(97)
        ).all()
    )
    rows.reverse()

    history: list[MetricPoint] = []
    previous_payload: dict[str, Any] | None = None
    for row in rows:
        payload = _safe_payload_json(row.payload_json)
        row_health = {
            "temperature_celsius": row.temperature_celsius,
            "memory_pressure_avg10": row.memory_pressure_avg10,
            "io_pressure_avg10": row.io_pressure_avg10,
            "filesystem_used_percent": row.filesystem_used_percent,
        }
        history.append(_prediction_point_from_health(row_health, previous_payload, payload))
        previous_payload = payload

    if len(history) > 96:
        history = history[-96:]

    current_point = _prediction_point_from_health(current_health, previous_payload, current_payload)
    return predict_hardware_drift(history, current_point)



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

    reliability = payload.get("memory_reliability") if isinstance(payload.get("memory_reliability"), dict) else {}
    ecc_corrected = _number(reliability, "corrected_errors") or 0
    ecc_uncorrected = _number(reliability, "uncorrected_errors") or 0
    if ecc_uncorrected > 0:
        score -= 45
        critical = True
        evidence.append(f"ECC uncorrected memory errors={int(ecc_uncorrected)}")
    elif ecc_corrected > 0:
        score -= min(20, 4 + int(min(ecc_corrected, 16)))
        evidence.append(f"ECC corrected memory errors={int(ecc_corrected)}")

    bmc = payload.get("bmc") if isinstance(payload.get("bmc"), dict) else {}
    bmc_critical = int(_number(bmc, "critical_count") or 0)
    bmc_warning = int(_number(bmc, "warning_count") or 0)
    if bmc_critical > 0:
        score -= min(40, 20 + bmc_critical * 5)
        critical = True
        evidence.append(f"BMC reports {bmc_critical} critical sensor condition(s)")
    elif bmc_warning > 0:
        score -= min(15, bmc_warning * 3)
        evidence.append(f"BMC reports {bmc_warning} warning sensor condition(s)")

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
        "ecc_corrected_errors": int(ecc_corrected),
        "ecc_uncorrected_errors": int(ecc_uncorrected),
        "bmc_critical_count": bmc_critical,
        "bmc_warning_count": bmc_warning,
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
    prediction = _prediction_for_server(db, server.id, health, payload.payload)
    active_maintenance = _active_maintenance(db, server.id, now)

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
        predictive_models_json=json.dumps(prediction.get("models") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    db.add(row)
    agent.last_seen_at = now
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Hardware telemetry nonce has already been used") from exc

    incident = _reconcile_hardware_incident(
        db,
        server,
        row,
        health,
        prediction,
        active_maintenance,
        now,
    )
    remediation_verification = _verify_completed_remediation(db, server.id, row, now)

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
        "incident": {
            "id": str(incident.id),
            "status": incident.status,
            "severity": incident.severity,
            "notification_suppressed": incident.notification_suppressed,
        } if incident is not None else None,
        "remediation_verification": remediation_verification,
        "maintenance": {
            "active": active_maintenance is not None,
            "suppress_notifications": bool(active_maintenance and active_maintenance.suppress_notifications),
            "ends_at": active_maintenance.ends_at.isoformat() if active_maintenance else None,
        },
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
            "models": json.loads(row.predictive_models_json or "{}"),
        },
        "sampled_at": row.issued_at.isoformat(),
        "received_at": row.created_at.isoformat() if row.created_at else None,
        "payload": json.loads(row.payload_json),
    }


@router.get("/incidents")
def list_hardware_incidents(
    status_filter: str = "open",
    limit: int = 100,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    query = select(HardwareIncident)
    if status_filter != "all":
        if status_filter not in {"open", "resolved"}:
            raise HTTPException(status_code=422, detail="status must be open, resolved or all")
        query = query.where(HardwareIncident.status == status_filter)
    rows = db.scalars(
        query.order_by(HardwareIncident.last_seen_at.desc()).limit(max(1, min(limit, 500)))
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "server_id": str(row.server_id),
                "latest_snapshot_id": str(row.latest_snapshot_id) if row.latest_snapshot_id else None,
                "kind": row.kind,
                "severity": row.severity,
                "status": row.status,
                "title": row.title,
                "summary": row.summary,
                "predictive_state": row.predictive_state,
                "predictive_risk_score": row.predictive_risk_score,
                "health_status": row.health_status,
                "notification_suppressed": row.notification_suppressed,
                "workflow_plan": json.loads(row.workflow_plan_json or "{}"),
                "opened_at": row.opened_at.isoformat() if row.opened_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            }
            for row in rows
        ]
    }


def _supervised_training_readiness(db: Session) -> dict[str, Any]:
    rows = db.execute(
        select(
            HardwareFailureLabel.label,
            HardwareFailureLabel.component,
            HardwareFailureLabel.confidence,
            HardwareFailureLabel.server_id,
        )
    ).all()
    return supervised_training_readiness([
        {
            "label": label,
            "component": component,
            "confidence": confidence,
            "server_id": server_id,
        }
        for label, component, confidence, server_id in rows
    ])


@router.post("/incidents/{incident_id}/failure-label")
def upsert_hardware_failure_label(
    incident_id: str,
    payload: FailureLabelUpsert,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    try:
        parsed = UUID(incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid hardware incident id") from exc

    incident = db.get(HardwareIncident, parsed)
    if incident is None:
        raise HTTPException(status_code=404, detail="Hardware incident not found")

    now = datetime.now(timezone.utc)
    row = db.scalar(
        select(HardwareFailureLabel).where(HardwareFailureLabel.incident_id == incident.id)
    )
    if row is None:
        row = HardwareFailureLabel(
            incident_id=incident.id,
            server_id=incident.server_id,
            snapshot_id=incident.latest_snapshot_id,
            label=payload.label,
            component=payload.component,
            confidence=payload.confidence,
            evidence=payload.evidence.strip(),
            confirmed_by_user_id=current.id,
            confirmed_at=now,
        )
        db.add(row)
    else:
        row.server_id = incident.server_id
        row.snapshot_id = incident.latest_snapshot_id
        row.label = payload.label
        row.component = payload.component
        row.confidence = payload.confidence
        row.evidence = payload.evidence.strip()
        row.confirmed_by_user_id = current.id
        row.confirmed_at = now

    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "incident_id": str(row.incident_id),
        "server_id": str(row.server_id),
        "snapshot_id": str(row.snapshot_id) if row.snapshot_id else None,
        "label": row.label,
        "component": row.component,
        "confidence": row.confidence,
        "evidence": row.evidence,
        "confirmed_by_user_id": str(row.confirmed_by_user_id) if row.confirmed_by_user_id else None,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "training_readiness": _supervised_training_readiness(db),
    }


@router.get("/failure-labels")
def list_hardware_failure_labels(
    limit: int = 100,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    rows = db.scalars(
        select(HardwareFailureLabel)
        .order_by(HardwareFailureLabel.confirmed_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return {
        "training_readiness": _supervised_training_readiness(db),
        "items": [
            {
                "id": str(row.id),
                "incident_id": str(row.incident_id),
                "server_id": str(row.server_id),
                "snapshot_id": str(row.snapshot_id) if row.snapshot_id else None,
                "label": row.label,
                "component": row.component,
                "confidence": row.confidence,
                "evidence": row.evidence,
                "confirmed_by_user_id": str(row.confirmed_by_user_id) if row.confirmed_by_user_id else None,
                "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
            }
            for row in rows
        ],
    }


@router.get("/operations-summary")
def hardware_operations_summary(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    incident_rows = dict(
        db.execute(
            select(HardwareIncident.severity, func.count(HardwareIncident.id))
            .where(HardwareIncident.status == "open")
            .group_by(HardwareIncident.severity)
        ).all()
    )
    task_rows = dict(
        db.execute(
            select(HardwareMaintenanceTask.status, func.count(HardwareMaintenanceTask.id))
            .group_by(HardwareMaintenanceTask.status)
        ).all()
    )
    delivery_rows = dict(
        db.execute(
            select(HardwareIncidentDelivery.status, func.count(HardwareIncidentDelivery.id))
            .group_by(HardwareIncidentDelivery.status)
        ).all()
    )
    return {
        "open_incidents": sum(int(value or 0) for value in incident_rows.values()),
        "incidents_by_severity": {str(key): int(value or 0) for key, value in incident_rows.items()},
        "tasks": {
            "open": int(task_rows.get("open", 0) or 0),
            "in_progress": int(task_rows.get("in_progress", 0) or 0),
            "completed": int(task_rows.get("completed", 0) or 0),
            "cancelled": int(task_rows.get("cancelled", 0) or 0),
        },
        "deliveries": {
            "queued": int(delivery_rows.get("queued", 0) or 0),
            "retry": int(delivery_rows.get("retry", 0) or 0),
            "delivered": int(delivery_rows.get("delivered", 0) or 0),
            "failed": int(delivery_rows.get("failed", 0) or 0),
            "cancelled": int(delivery_rows.get("cancelled", 0) or 0),
        },
        "supervised_learning": _supervised_training_readiness(db),
    }


@router.post("/incidents/{incident_id}/retry-notifications")
def retry_hardware_incident_notifications(
    incident_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    try:
        parsed = UUID(incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid hardware incident id") from exc

    incident = db.get(HardwareIncident, parsed)
    if incident is None:
        raise HTTPException(status_code=404, detail="Hardware incident not found")
    if incident.status != "open":
        raise HTTPException(status_code=409, detail="Resolved hardware incidents cannot resend notifications")
    if incident.notification_suppressed:
        raise HTTPException(status_code=409, detail="Notifications are suppressed by an active maintenance window")

    rows = list(
        db.scalars(
            select(HardwareIncidentDelivery).where(
                HardwareIncidentDelivery.incident_id == incident.id,
                HardwareIncidentDelivery.status.in_(["failed", "retry"]),
            )
        ).all()
    )
    for row in rows:
        row.status = "queued"
        row.attempts = 0
        row.next_attempt_at = None
        row.last_error = None
        row.delivered_at = None
    db.commit()
    return {"incident_id": str(incident.id), "requeued": len(rows)}


@router.get("/maintenance-tasks")
def list_hardware_maintenance_tasks(
    status_filter: str = "open",
    limit: int = 100,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    query = select(HardwareMaintenanceTask)
    if status_filter != "all":
        if status_filter not in {"open", "in_progress", "completed", "cancelled"}:
            raise HTTPException(status_code=422, detail="invalid maintenance task status")
        query = query.where(HardwareMaintenanceTask.status == status_filter)
    rows = db.scalars(
        query.order_by(HardwareMaintenanceTask.created_at.desc()).limit(max(1, min(limit, 500)))
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "incident_id": str(row.incident_id),
                "server_id": str(row.server_id),
                "priority": row.priority,
                "status": row.status,
                "title": row.title,
                "description": row.description,
                "assigned_to_user_id": str(row.assigned_to_user_id) if row.assigned_to_user_id else None,
                "completed_by_user_id": str(row.completed_by_user_id) if row.completed_by_user_id else None,
                "completion_note": row.completion_note,
                "remediation_action": row.remediation_action,
                "remediation_outcome": row.remediation_outcome,
                "outcome_recorded_at": row.outcome_recorded_at.isoformat() if row.outcome_recorded_at else None,
                "measured_outcome": row.measured_outcome,
                "verification_confidence": row.verification_confidence,
                "verification_sample_count": row.verification_sample_count,
                "verification_evidence": json.loads(row.verification_evidence_json or "[]"),
                "verification_evaluated_at": row.verification_evaluated_at.isoformat() if row.verification_evaluated_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    }


@router.post("/maintenance-tasks/{task_id}/status")
def update_hardware_maintenance_task(
    task_id: str,
    payload: MaintenanceTaskUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    try:
        parsed = UUID(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid hardware maintenance task id") from exc

    row = db.get(HardwareMaintenanceTask, parsed)
    if row is None:
        raise HTTPException(status_code=404, detail="Hardware maintenance task not found")
    if row.status in {"completed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Hardware maintenance task is already closed")

    now = datetime.now(timezone.utc)
    row.status = payload.status
    incident = db.get(HardwareIncident, row.incident_id)
    if payload.status in {"in_progress", "completed"} and row.remediation_baseline_snapshot_id is None and incident is not None:
        row.remediation_baseline_snapshot_id = incident.latest_snapshot_id
    if row.assigned_to_user_id is None:
        row.assigned_to_user_id = current.id
    if payload.status in {"completed", "cancelled"}:
        row.completed_at = now
        row.completed_by_user_id = current.id
        row.completion_note = payload.note.strip()
        if payload.status == "completed":
            row.remediation_action = payload.remediation_action.strip()
            row.remediation_outcome = payload.outcome.strip()
            row.outcome_recorded_at = now if row.remediation_action and row.remediation_outcome else None
    elif payload.status == "in_progress":
        row.completed_at = None
        row.completed_by_user_id = None
        row.completion_note = payload.note.strip()
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "incident_id": str(row.incident_id),
        "server_id": str(row.server_id),
        "priority": row.priority,
        "status": row.status,
        "assigned_to_user_id": str(row.assigned_to_user_id) if row.assigned_to_user_id else None,
        "completed_by_user_id": str(row.completed_by_user_id) if row.completed_by_user_id else None,
        "completion_note": row.completion_note,
        "remediation_action": row.remediation_action,
        "remediation_outcome": row.remediation_outcome,
        "outcome_recorded_at": row.outcome_recorded_at.isoformat() if row.outcome_recorded_at else None,
        "measured_outcome": row.measured_outcome,
        "verification_confidence": row.verification_confidence,
        "verification_sample_count": row.verification_sample_count,
        "verification_evidence": json.loads(row.verification_evidence_json or "[]"),
        "verification_evaluated_at": row.verification_evaluated_at.isoformat() if row.verification_evaluated_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
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
        maintenance = _active_maintenance(db, server.id, now)
        acknowledgement = _ack_for_snapshot(db, latest.id if latest else None)
        incident = _active_hardware_incident(db, server.id)
        maintenance_task = db.scalar(
            select(HardwareMaintenanceTask).where(HardwareMaintenanceTask.incident_id == incident.id)
        ) if incident else None
        failure_label = db.scalar(
            select(HardwareFailureLabel).where(HardwareFailureLabel.incident_id == incident.id)
        ) if incident else None
        latest_remediation_task = db.scalar(
            select(HardwareMaintenanceTask)
            .where(
                HardwareMaintenanceTask.server_id == server.id,
                HardwareMaintenanceTask.status == "completed",
                HardwareMaintenanceTask.remediation_action != "",
            )
            .order_by(HardwareMaintenanceTask.completed_at.desc())
            .limit(1)
        )
        incident_deliveries = list(
            db.scalars(
                select(HardwareIncidentDelivery).where(HardwareIncidentDelivery.incident_id == incident.id)
            ).all()
        ) if incident else []

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
        ebpf = payload.get("ebpf") if isinstance(payload.get("ebpf"), dict) else {}
        cpu_native = payload.get("cpu_native") if isinstance(payload.get("cpu_native"), dict) else {}

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
            "ecc_corrected_errors": int(_number(payload.get("memory_reliability") if isinstance(payload.get("memory_reliability"), dict) else {}, "corrected_errors") or 0),
            "ecc_uncorrected_errors": int(_number(payload.get("memory_reliability") if isinstance(payload.get("memory_reliability"), dict) else {}, "uncorrected_errors") or 0),
            "bmc_critical_count": int(_number(payload.get("bmc") if isinstance(payload.get("bmc"), dict) else {}, "critical_count") or 0),
            "bmc_warning_count": int(_number(payload.get("bmc") if isinstance(payload.get("bmc"), dict) else {}, "warning_count") or 0),
            "ebpf_block_latency_p50_ms": _number(ebpf, "block_latency_p50_ms"),
            "ebpf_block_latency_p95_ms": _number(ebpf, "block_latency_p95_ms"),
            "ebpf_block_latency_p99_ms": _number(ebpf, "block_latency_p99_ms"),
            "ebpf_block_latency_max_ms": _number(ebpf, "block_latency_max_ms"),
            "ebpf_latency_percentiles_capped": bool(ebpf.get("block_latency_percentiles_capped")),
            "cpu_native": {
                "available": bool(cpu_native.get("available")),
                "vendor": str(cpu_native.get("vendor") or "")[:12],
                "family": int(_number(cpu_native, "family") or 0),
                "model": int(_number(cpu_native, "model") or 0),
                "stepping": int(_number(cpu_native, "stepping") or 0),
                "invariant_tsc": bool(cpu_native.get("invariant_tsc")),
                "rdtscp": bool(cpu_native.get("rdtscp")),
                "aes_ni": bool(cpu_native.get("aes_ni")),
                "avx": bool(cpu_native.get("avx")),
                "avx2": bool(cpu_native.get("avx2")),
                "vmx": bool(cpu_native.get("vmx")),
                "svm": bool(cpu_native.get("svm")),
                "hypervisor_present": bool(cpu_native.get("hypervisor_present")),
                "hypervisor_vendor": str(cpu_native.get("hypervisor_vendor") or "")[:12],
                "logical_processors": int(_number(cpu_native, "logical_processors") or 0),
            },
            "predictive_risk_score": latest.predictive_risk_score if latest else None,
            "predictive_state": predictive_state,
            "predictive_confidence": latest.predictive_confidence if latest else None,
            "predictive_evidence": json.loads(latest.predictive_evidence_json or "[]") if latest else [],
            "predictive_models": json.loads(latest.predictive_models_json or "{}") if latest else {},
            "evidence": evidence,
            "sampled_at": latest.issued_at.isoformat() if latest else None,
            "maintenance": {
                "active": maintenance is not None,
                "reason": maintenance.reason if maintenance else None,
                "ends_at": maintenance.ends_at.isoformat() if maintenance else None,
                "suppress_notifications": bool(maintenance and maintenance.suppress_notifications),
            },
            "latest_remediation": {
                "id": str(latest_remediation_task.id),
                "remediation_action": latest_remediation_task.remediation_action,
                "reported_outcome": latest_remediation_task.remediation_outcome,
                "measured_outcome": latest_remediation_task.measured_outcome,
                "verification_confidence": latest_remediation_task.verification_confidence,
                "verification_sample_count": latest_remediation_task.verification_sample_count,
                "verification_evidence": json.loads(latest_remediation_task.verification_evidence_json or "[]"),
                "verification_evaluated_at": latest_remediation_task.verification_evaluated_at.isoformat() if latest_remediation_task.verification_evaluated_at else None,
                "completed_at": latest_remediation_task.completed_at.isoformat() if latest_remediation_task.completed_at else None,
            } if latest_remediation_task else None,
            "acknowledgement": {
                "acknowledged": acknowledgement is not None,
                "note": acknowledgement.note if acknowledgement else None,
                "acknowledged_at": acknowledgement.acknowledged_at.isoformat() if acknowledgement else None,
            },
            "incident": {
                "id": str(incident.id),
                "severity": incident.severity,
                "status": incident.status,
                "title": incident.title,
                "summary": incident.summary,
                "predictive_state": incident.predictive_state,
                "predictive_risk_score": incident.predictive_risk_score,
                "notification_suppressed": incident.notification_suppressed,
                "workflow_plan": json.loads(incident.workflow_plan_json or "{}"),
                "failure_label": {
                    "id": str(failure_label.id),
                    "label": failure_label.label,
                    "component": failure_label.component,
                    "confidence": failure_label.confidence,
                    "evidence": failure_label.evidence,
                    "confirmed_at": failure_label.confirmed_at.isoformat() if failure_label.confirmed_at else None,
                } if failure_label else None,
                "deliveries": [
                    {
                        "channel": delivery.channel,
                        "status": delivery.status,
                        "attempts": delivery.attempts,
                        "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
                    }
                    for delivery in incident_deliveries
                ],
                "maintenance_task": {
                    "id": str(maintenance_task.id),
                    "priority": maintenance_task.priority,
                    "status": maintenance_task.status,
                    "assigned_to_user_id": str(maintenance_task.assigned_to_user_id) if maintenance_task.assigned_to_user_id else None,
                    "completion_note": maintenance_task.completion_note,
                    "remediation_action": maintenance_task.remediation_action,
                    "remediation_outcome": maintenance_task.remediation_outcome,
                    "outcome_recorded_at": maintenance_task.outcome_recorded_at.isoformat() if maintenance_task.outcome_recorded_at else None,
                    "measured_outcome": maintenance_task.measured_outcome,
                    "verification_confidence": maintenance_task.verification_confidence,
                    "verification_sample_count": maintenance_task.verification_sample_count,
                    "verification_evidence": json.loads(maintenance_task.verification_evidence_json or "[]"),
                    "verification_evaluated_at": maintenance_task.verification_evaluated_at.isoformat() if maintenance_task.verification_evaluated_at else None,
                    "completed_at": maintenance_task.completed_at.isoformat() if maintenance_task.completed_at else None,
                } if maintenance_task else None,
                "opened_at": incident.opened_at.isoformat() if incident.opened_at else None,
                "last_seen_at": incident.last_seen_at.isoformat() if incident.last_seen_at else None,
            } if incident else None,
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


@router.get("/servers/{server_id}/maintenance-windows")
def list_hardware_maintenance_windows(
    server_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    try:
        parsed = UUID(server_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid infrastructure server id") from exc
    if db.get(InfrastructureServer, parsed) is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")

    rows = db.scalars(
        select(HardwareMaintenanceWindow)
        .where(HardwareMaintenanceWindow.server_id == parsed)
        .order_by(HardwareMaintenanceWindow.starts_at.desc())
        .limit(100)
    ).all()
    now = datetime.now(timezone.utc)
    return {
        "server_id": server_id,
        "items": [
            {
                "id": str(row.id),
                "starts_at": row.starts_at.isoformat(),
                "ends_at": row.ends_at.isoformat(),
                "reason": row.reason,
                "suppress_notifications": row.suppress_notifications,
                "active": _window_active_at(row, now),
                "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.post("/servers/{server_id}/maintenance-windows", status_code=201)
def create_hardware_maintenance_window(
    server_id: str,
    body: MaintenanceWindowCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    try:
        parsed = UUID(server_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid infrastructure server id") from exc
    if db.get(InfrastructureServer, parsed) is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")

    starts_at = _utc(body.starts_at)
    ends_at = _utc(body.ends_at)
    if ends_at <= starts_at:
        raise HTTPException(status_code=422, detail="Maintenance end must be after start")
    if ends_at - starts_at > timedelta(days=30):
        raise HTTPException(status_code=422, detail="Maintenance window cannot exceed 30 days")
    if ends_at <= datetime.now(timezone.utc) - timedelta(minutes=1):
        raise HTTPException(status_code=422, detail="Maintenance window has already ended")

    row = HardwareMaintenanceWindow(
        server_id=parsed,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=body.reason.strip(),
        suppress_notifications=body.suppress_notifications,
        created_by_user_id=current.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "server_id": server_id,
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
        "reason": row.reason,
        "suppress_notifications": row.suppress_notifications,
    }


@router.delete("/maintenance-windows/{window_id}", status_code=204)
def cancel_hardware_maintenance_window(
    window_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    try:
        parsed = UUID(window_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid maintenance window id") from exc
    row = db.get(HardwareMaintenanceWindow, parsed)
    if row is None:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    if row.cancelled_at is None:
        row.cancelled_at = datetime.now(timezone.utc)
        db.commit()
    return None


@router.post("/servers/{server_id}/acknowledge", status_code=201)
def acknowledge_hardware_alert(
    server_id: str,
    body: AlertAcknowledgementCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    try:
        parsed = UUID(server_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid infrastructure server id") from exc
    if db.get(InfrastructureServer, parsed) is None:
        raise HTTPException(status_code=404, detail="Infrastructure server not found")

    latest = db.scalar(
        select(HardwareTelemetrySnapshot)
        .where(HardwareTelemetrySnapshot.server_id == parsed)
        .order_by(HardwareTelemetrySnapshot.created_at.desc())
    )
    if latest is None:
        raise HTTPException(status_code=404, detail="No hardware telemetry to acknowledge")

    existing = _ack_for_snapshot(db, latest.id)
    if existing is not None:
        return {
            "id": str(existing.id),
            "snapshot_id": str(existing.snapshot_id),
            "acknowledged_at": existing.acknowledged_at.isoformat(),
            "note": existing.note,
            "already_acknowledged": True,
        }

    row = HardwareAlertAcknowledgement(
        server_id=parsed,
        snapshot_id=latest.id,
        acknowledged_by_user_id=current.id,
        note=body.note.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "snapshot_id": str(row.snapshot_id),
        "acknowledged_at": row.acknowledged_at.isoformat(),
        "note": row.note,
        "already_acknowledged": False,
    }
