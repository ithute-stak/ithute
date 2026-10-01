from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PlatformConfiguration


def effective_platform_mode(db: Session) -> str:
    """Return the effective platform mode used by public onboarding.

    A fresh database may still contain the historical ``bootstrap`` row while the
    production deployment explicitly declares ``PLATFORM_MODE=domain``. Treat that
    exact combination as an already-deployed domain platform. Any real persisted
    setup transition (domain_pending/domain_verified/domain_active) remains
    authoritative, so an in-progress setup is never skipped.
    """

    current = db.scalar(
        select(PlatformConfiguration).order_by(PlatformConfiguration.created_at.asc())
    )
    if current and current.mode and current.mode != "bootstrap":
        return current.mode
    if settings.platform_mode == "domain":
        return "domain_active"
    return current.mode if current and current.mode else "bootstrap"


def public_signup_enabled(db: Session) -> bool:
    mode = effective_platform_mode(db)
    if mode == "bootstrap":
        return settings.platform_bootstrap_signup_enabled
    if mode == "domain_active":
        return settings.platform_domain_signup_enabled
    return False
