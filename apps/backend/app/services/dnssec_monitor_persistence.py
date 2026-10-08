"""Transactional DNSSEC incident persistence.

Caller owns commit/rollback. Domain row locking serializes monitoring writes even
when the state row has not yet been created.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domains import Domain
from app.models.business import Notification
from app.models.dnssec_incident_history import DnssecIncidentHistory, DnssecMonitorState
from app.services.dnssec_monitor_state import MonitorState, transition


def record_dnssec_observation(db: Session, *, tenant_id: UUID, domain_id: UUID,
                              observation: dict, checked_at: datetime | None = None,
                              threshold: int = 3) -> dict:
    """Persist an observation in the caller's transaction, never commit internally."""
    now = checked_at or datetime.now(timezone.utc)
    domain = db.execute(
        select(Domain).where(Domain.id == domain_id, Domain.tenant_id == tenant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if domain is None:
        raise ValueError("Domain not found for tenant")

    state = db.get(DnssecMonitorState, domain_id)
    if state is None:
        state = DnssecMonitorState(domain_id=domain_id, tenant_id=tenant_id)
        db.add(state)
        previous = MonitorState()
    else:
        if state.tenant_id != tenant_id:
            raise ValueError("Monitoring state tenant mismatch")
        previous = MonitorState(state.code, state.failures, state.status)

    next_state, events = transition(previous, observation, threshold=threshold)
    state.code = next_state.code
    state.failures = next_state.failures
    state.status = next_state.status
    state.last_checked_at = now
    state.updated_at = now

    # Recovery also closes a preceding open incident when a different failure
    # was pending confirmation at the time the DNSSEC answer became healthy.
    if observation.get("severity") == "healthy":
        unresolved = db.execute(
            select(DnssecIncidentHistory).where(
                DnssecIncidentHistory.tenant_id == tenant_id,
                DnssecIncidentHistory.domain_id == domain_id,
                DnssecIncidentHistory.status.in_(("open", "acknowledged")),
            ).with_for_update()
        ).scalars().all()
        for incident in unresolved:
            incident.status = "recovered"
            incident.recovered_at = now
        if unresolved and "recovered" not in events:
            events.append("recovered")

    # A new confirmed failure supersedes an older open incident for this
    # domain. Keep the old incident active while the new failure is pending.
    if "opened" in events:
        stale = db.execute(
            select(DnssecIncidentHistory).where(
                DnssecIncidentHistory.tenant_id == tenant_id,
                DnssecIncidentHistory.domain_id == domain_id,
                DnssecIncidentHistory.code != next_state.code,
                DnssecIncidentHistory.status.in_(("open", "acknowledged")),
            ).with_for_update()
        ).scalars().all()
        for incident in stale:
            incident.status = "superseded"
            incident.recovered_at = None

    if "opened" in events:
        existing = db.execute(
            select(DnssecIncidentHistory).where(
                DnssecIncidentHistory.tenant_id == tenant_id,
                DnssecIncidentHistory.domain_id == domain_id,
                DnssecIncidentHistory.code == next_state.code,
                DnssecIncidentHistory.status.in_(("open", "acknowledged")),
            ).with_for_update()
        ).scalars().first()
        if existing is None:
            db.add(DnssecIncidentHistory(
                tenant_id=tenant_id, domain_id=domain_id,
                code=next_state.code,
                severity=observation["severity"],
                summary=observation.get("summary") or next_state.code,
                status="open", opened_at=now,
            ))
        else:
            events = []

    # Notifications are persisted with the incident in the same transaction.
    # Events only fire on transitions, so steady-state checks create no spam.
    if "opened" in events:
        db.add(Notification(
            tenant_id=tenant_id, category="dnssec", severity="warning",
            title=f"DNSSEC incident detected: {domain.ascii_name}",
            message=(observation.get("summary") or next_state.code or "DNSSEC requires attention")[:1000],
            action_url="/dns-security",
        ))
    if "recovered" in events:
        db.add(Notification(
            tenant_id=tenant_id, category="dnssec", severity="success",
            title=f"DNSSEC incident recovered: {domain.ascii_name}",
            message="Previously reported DNSSEC monitoring incidents have recovered.",
            action_url="/dns-security",
        ))

    db.flush()
    return {"status": next_state.status, "code": next_state.code,
            "failures": next_state.failures, "events": events}
