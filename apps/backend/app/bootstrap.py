from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User
from app.services.billing import ensure_default_plans
from app.services.system_mailboxes import ensure_system_mailboxes


def main():
    with SessionLocal() as db:
        ensure_default_plans(db)
        email = settings.bootstrap_admin_email.lower().strip()
        owner = db.scalar(select(User).where(User.email == email))
        now = datetime.now(timezone.utc)
        created_owner = owner is None

        if owner is None:
            owner = User(
                email=email,
                password_hash=hash_password(settings.bootstrap_admin_password),
                full_name="Platform Owner",
                is_platform_owner=True,
                is_active=True,
                email_verified_at=now,
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)
        else:
            owner.password_hash = hash_password(settings.bootstrap_admin_password)
            owner.is_platform_owner = True
            owner.is_active = True
            owner.email_verified_at = owner.email_verified_at or now
            if not owner.full_name.strip():
                owner.full_name = "Platform Owner"
            db.commit()
            db.refresh(owner)

        result = ensure_system_mailboxes(db, owner)
        owner_action = "created" if created_owner else "synchronized"
        print(f"Bootstrap platform owner {owner_action}: {email}")
        print(
            "System mailboxes synchronized: "
            + ", ".join(result.addresses)
            + (f"; created={len(result.created_addresses)}" if result.created_addresses else "; created=0")
        )


if __name__ == "__main__":
    main()
