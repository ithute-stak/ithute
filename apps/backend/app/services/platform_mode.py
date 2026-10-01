from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PlatformConfiguration


def effective_platform_mode(db: Session) -> str:
    """Return the persisted platform mode when setup has already activated it.

    The environment value remains the bootstrap fallback for fresh installs, but once
    the platform owner has completed setup the database configuration is authoritative.
    """

    current = db.scalar(select(PlatformConfiguration).order_by(PlatformConfiguration.created_at.asc()))
    if current and current.mode:
        return current.mode
    return settings.platform_mode


def public_signup_enabled(db: Session) -> bool:
    mode = effective_platform_mode(db)
    if mode == "bootstrap":
        return settings.platform_bootstrap_signup_enabled
    return settings.platform_domain_signup_enabled
