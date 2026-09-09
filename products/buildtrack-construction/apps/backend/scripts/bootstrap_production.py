#!/usr/bin/env python3
"""Idempotent production bootstrap for Nthane Brothers BuildTrack.

Central Ithute Auth owns the real credential. The local User row is only the
BuildTrack role/scope projection and receives an unreachable random legacy hash.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select

from app.api.v1.access import ensure_phase2_access_catalog
from app.api.v1.foundation import BootstrapRequest, bootstrap
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Company, Role, User, UserRoleAssignment
from app.security.access import hash_password


def main() -> None:
    settings = get_settings()
    email = settings.superadmin_email.strip().lower()
    if not email or "@" not in email:
        raise SystemExit("SUPERADMIN_EMAIL must be a valid email address")

    with SessionLocal() as db:
        company = db.scalar(select(Company).order_by(Company.id).limit(1))
        if company is None:
            bootstrap(
                BootstrapRequest(
                    name="Nthane Brothers",
                    legal_name="Nthane Brothers",
                    code="NTHANE",
                    head_office_name="Head Office",
                    head_office_code="HO",
                    head_office_district="Maseru",
                    actor="Ithute production bootstrap",
                ),
                db=db,
            )
            company = db.scalar(select(Company).order_by(Company.id).limit(1))

        if company is None:
            raise SystemExit("BuildTrack company bootstrap failed")

        ensure_phase2_access_catalog(db, company)
        system_admin = db.scalar(
            select(Role).where(Role.company_id == company.id, Role.code == "SYSTEM_ADMIN")
        )
        if system_admin is None:
            raise SystemExit("SYSTEM_ADMIN role is missing after BuildTrack bootstrap")

        user = db.scalar(select(User).where(User.company_id == company.id, User.email == email))
        if user is None:
            base_username = email.split("@", 1)[0][:72] or "superadmin"
            username = base_username
            suffix = 1
            while db.scalar(
                select(User.id).where(User.company_id == company.id, User.username == username)
            ):
                suffix += 1
                username = f"{base_username[:70]}-{suffix}"
            user = User(
                company_id=company.id,
                username=username,
                email=email,
                full_name="Nthane Brothers Super Administrator",
                job_title="System Administrator",
                password_hash=hash_password(secrets.token_urlsafe(48)),
                must_change_password=False,
                status="active",
                is_active=True,
                created_by="Ithute production bootstrap",
            )
            db.add(user)
            db.flush()
        else:
            user.is_active = True
            user.status = "active"
            user.must_change_password = False

        assignment = db.scalar(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user.id,
                UserRoleAssignment.role_id == system_admin.id,
            )
        )
        if assignment is None:
            db.add(
                UserRoleAssignment(
                    user_id=user.id,
                    role_id=system_admin.id,
                    is_primary=True,
                    created_by="Ithute production bootstrap",
                )
            )

        db.commit()
        print(f"BuildTrack production owner projection ready for {email}")


if __name__ == "__main__":
    main()
