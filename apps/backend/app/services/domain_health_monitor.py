from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Domain, DomainHealthMonitorState, Notification
from app.models.domains import DomainStatus
from app.services.domain_mail_health import domain_mail_health


def _failing_checks(health: dict) -> list[str]:
    return [
        str(item.get("id"))
        for item in health.get("checks", [])
        if item.get("required") and item.get("status") != "healthy"
    ]


def run_domain_health_monitor(db: Session) -> dict:
    domains = db.scalars(
        select(Domain).where(
            Domain.mail_enabled.is_(True),
            Domain.status != DomainStatus.archived,
        )
    ).all()

    checked = 0
    degraded = 0
    recovered = 0
    notified = 0
    failures: list[dict] = []
    now = datetime.now(timezone.utc)

    for domain in domains:
        try:
            health = domain_mail_health(db, domain)
        except Exception as exc:
            failures.append({"domain": domain.ascii_name, "error": str(exc)[:240]})
            continue

        checked += 1
        current = str(health.get("overall_status") or "attention")
        score = int(health.get("score") or 0)
        failing = _failing_checks(health)

        state = db.get(DomainHealthMonitorState, domain.id)
        previous = state.last_status if state else None
        if state is None:
            state = DomainHealthMonitorState(domain_id=domain.id, tenant_id=domain.tenant_id)
            db.add(state)

        state.last_status = current
        state.last_score = score
        state.failing_checks_json = json.dumps(failing, sort_keys=True)
        state.last_checked_at = now

        if current != "healthy":
            degraded += 1
            if state.first_unhealthy_at is None:
                state.first_unhealthy_at = now
            state.recovered_at = None
            if previous in {None, "healthy"}:
                title = f"Mail health issue detected for {domain.ascii_name}"
                message = (
                    f"Ithute detected required mail-health checks needing attention "
                    f"({', '.join(failing) if failing else 'unknown'}). Current readiness score: {score}%."
                )
                db.add(
                    Notification(
                        tenant_id=domain.tenant_id,
                        category="mail-health",
                        severity="warning",
                        title=title,
                        message=message,
                        action_url="/domain-health",
                    )
                )
                state.last_notified_at = now
                notified += 1
        else:
            if previous not in {None, "healthy"}:
                recovered += 1
                db.add(
                    Notification(
                        tenant_id=domain.tenant_id,
                        category="mail-health",
                        severity="success",
                        title=f"Mail health recovered for {domain.ascii_name}",
                        message="All required Ithute mail-domain health checks are passing again.",
                        action_url="/domain-health",
                    )
                )
                state.last_notified_at = now
                notified += 1
            state.first_unhealthy_at = None
            state.recovered_at = now

    db.commit()
    return {
        "checked": checked,
        "degraded": degraded,
        "recovered": recovered,
        "notifications_created": notified,
        "failures": failures,
    }
