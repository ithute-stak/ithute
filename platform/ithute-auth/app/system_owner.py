from __future__ import annotations

from sqlalchemy import select, update

from .config import get_settings
from .db import SessionLocal
from .models import AuthSession, User, utcnow
from .security import hash_password, normalize_email, verify_password


DISPLAY_NAME = "Ithute System Owner"


def synchronize_system_owner() -> User | None:
    """Make the configured global owner authoritative inside central Auth only.

    The plaintext password exists only in the Auth process environment. Product
    databases receive the signed ``is_platform_admin`` claim and never receive
    or persist this credential.
    """

    settings = get_settings()
    email = normalize_email(settings.system_owner_email)
    password = settings.system_owner_password

    # An unset secret must not break an otherwise healthy deployment. This lets
    # the code be deployed before the protected production secret is populated.
    if not email and not password:
        print("Central system owner provisioning is not configured.")
        return None
    if not email:
        raise RuntimeError("AUTH_SYSTEM_OWNER_EMAIL is required when the system owner password is configured")
    if not password:
        print("Central system owner password is not configured; owner synchronization skipped.")
        return None
    if len(password) < 12:
        raise RuntimeError("AUTH_SYSTEM_OWNER_PASSWORD must contain at least 12 characters")

    now = utcnow()
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == email))
        created = owner is None
        password_changed = False

        if owner is None:
            owner = User(
                email=email,
                phone=None,
                display_name=DISPLAY_NAME,
                password_hash=hash_password(password),
                is_active=True,
                is_platform_admin=True,
                email_verified=True,
                phone_verified=False,
                password_changed_at=now,
            )
            db.add(owner)
            db.flush()
            password_changed = True
        else:
            owner.display_name = owner.display_name.strip() or DISPLAY_NAME
            owner.is_active = True
            owner.is_platform_admin = True
            owner.email_verified = True
            if not verify_password(password, owner.password_hash):
                owner.password_hash = hash_password(password)
                owner.password_changed_at = now
                owner.security_version += 1
                password_changed = True

        # The configured identity is the single global human system owner.
        db.execute(
            update(User)
            .where(User.id != owner.id, User.is_platform_admin.is_(True))
            .values(is_platform_admin=False)
        )

        if password_changed and not created:
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == owner.id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=now, revoked_reason="system_owner_password_rotated")
            )

        db.commit()
        db.refresh(owner)

    action = "created" if created else "synchronized"
    print(f"Central Ithute system owner {action}: {email}")
    return owner


def main() -> None:
    synchronize_system_owner()


if __name__ == "__main__":
    main()
