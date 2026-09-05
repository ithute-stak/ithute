from __future__ import annotations

import os
import secrets
import uuid

from sqlalchemy.orm import Session

from database.session import SessionLocal
from database.multi_tenant_school_management.models import User, Grade, Class
from database.multi_tenant_school_management.schemas.user import UserRole
from utils.auth.password_hash_verify import hash_password


def seed_super_admin(db: Session):
    """Optionally bootstrap a super admin by explicit central Auth subject.

    No fixed local credential is created. The random legacy password is never
    printed or persisted outside the hash and therefore cannot be used to log in.
    """
    raw_subject = os.getenv("TUTOR_BOOTSTRAP_AUTH_USER_ID", "").strip()
    if not raw_subject:
        return

    try:
        auth_user_id = uuid.UUID(raw_subject)
    except ValueError as exc:
        raise RuntimeError("TUTOR_BOOTSTRAP_AUTH_USER_ID must be a UUID") from exc

    existing = db.query(User).filter(User.auth_user_id == auth_user_id).first()
    if existing:
        if existing.role != UserRole.super_admin:
            existing.role = UserRole.super_admin
        return

    email = os.getenv("TUTOR_BOOTSTRAP_ADMIN_EMAIL", "").strip()
    if not email:
        raise RuntimeError("TUTOR_BOOTSTRAP_ADMIN_EMAIL is required with TUTOR_BOOTSTRAP_AUTH_USER_ID")

    user = User(
        auth_user_id=auth_user_id,
        username=os.getenv("TUTOR_BOOTSTRAP_ADMIN_USERNAME", "superadmin").strip() or "superadmin",
        email=email,
        password=hash_password(secrets.token_urlsafe(48)),
        role=UserRole.super_admin,
        school_id=None,
    )
    db.add(user)
    db.flush()
    print("Tutor central-auth super admin profile created")


def seed_grades_and_classes(db: Session):
    grade_names = ["Grade-R"] + [f"Grade-{i}" for i in range(1, 13)]

    for grade_name in grade_names:
        grade = db.query(Grade).filter(Grade.name == grade_name).first()
        if not grade:
            grade = Grade(name=grade_name)
            db.add(grade)
            db.flush()

        for i in range(1, 6):
            class_name = f"{grade_name}_{i}"
            existing_class = (
                db.query(Class)
                .filter(Class.name == class_name, Class.grade_id == grade.id)
                .first()
            )
            if existing_class:
                continue
            db.add(Class(name=class_name, grade_id=grade.id))


def run_startup_seed():
    db = SessionLocal()
    try:
        seed_super_admin(db)
        seed_grades_and_classes(db)
        db.commit()
        print("Tutor startup seed completed")
    except Exception as exc:
        db.rollback()
        print(f"Tutor startup seed failed: {exc}")
        raise
    finally:
        db.close()
