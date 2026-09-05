import os
import uuid

os.environ.setdefault("AUTH_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base
from app.models import AuditEvent
from app.security_service import verification_confirmation_rate_limited


def test_verification_confirmation_failures_are_rate_limited_per_user() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    user_id = uuid.uuid4()
    settings = Settings(
        database_url="sqlite://",
        verification_confirm_rate_window_seconds=900,
        verification_confirm_max_failures_per_user=2,
    )

    with Session(engine) as db:
        db.add(AuditEvent(user_id=user_id, event_type="email_verification_failed", success=False))
        db.add(AuditEvent(user_id=user_id, event_type="phone_verification_failed", success=False))
        db.commit()
        assert verification_confirmation_rate_limited(db, user_id=user_id, settings=settings) is True


def test_successes_and_other_users_do_not_count_as_failures() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    settings = Settings(
        database_url="sqlite://",
        verification_confirm_rate_window_seconds=900,
        verification_confirm_max_failures_per_user=2,
    )

    with Session(engine) as db:
        db.add(AuditEvent(user_id=user_id, event_type="email_verified", success=True))
        db.add(AuditEvent(user_id=other_user_id, event_type="email_verification_failed", success=False))
        db.commit()
        assert verification_confirmation_rate_limited(db, user_id=user_id, settings=settings) is False
