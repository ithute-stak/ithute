#!/usr/bin/env python3
"""Provision the NBros login account from runtime-only environment secrets.

This script deliberately never accepts a password on the command line and never
prints it. It is intended to be executed inside the central Ithute Auth
container by the production provisioning workflow.
"""
from __future__ import annotations

import os

from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import AuthSession, User, utcnow
from app.security import hash_password, normalize_email, verify_password


def _required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> int:
    email = normalize_email(_required_env("NBROS_ADMIN_EMAIL"))
    password = _required_env("NBROS_ADMIN_PASSWORD")
    if not email or "@" not in email:
        raise SystemExit("NBROS_ADMIN_EMAIL must be a valid email address")
    if len(password) < 12 or len(password) > 128:
        raise SystemExit("NBROS_ADMIN_PASSWORD must be between 12 and 128 characters")

    now = utcnow()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        created = user is None
        password_changed = False

        if user is None:
            user = User(
                email=email,
                phone=None,
                display_name="NBros Administrator",
                password_hash=hash_password(password),
                is_active=True,
                email_verified=True,
            )
            db.add(user)
            db.flush()
            password_changed = True
        else:
            user.is_active = True
            user.email_verified = True
            user.failed_login_attempts = 0
            user.locked_until = None
            if not user.display_name.strip():
                user.display_name = "NBros Administrator"
            if not verify_password(password, user.password_hash):
                user.password_hash = hash_password(password)
                user.password_changed_at = now
                user.security_version += 1
                password_changed = True

        if password_changed:
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=now, revoked_reason="nbros_admin_password_provisioned")
            )

        db.commit()
        action = "created" if created else ("updated" if password_changed else "verified")
        print(f"NBros central-auth account {action}: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
