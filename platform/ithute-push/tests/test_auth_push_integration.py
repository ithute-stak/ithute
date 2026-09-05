import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

os.environ.setdefault("PUSH_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("PUSH_ENDPOINT_ENCRYPTION_KEY", Fernet.generate_key().decode())

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import AuthError, AuthVerifier, LifecyclePrincipal, UserPrincipal
from app.config import Settings
from app.db import Base
from app.main import apply_auth_event, require_live_user_state
from app.models import ApplicationState, AuthLifecycleEvent, AuthUserState, RevokedAuthSession
from app.schemas import AuthLifecycleEventRequest


def _verifier() -> AuthVerifier:
    settings = Settings(
        database_url="sqlite://",
        endpoint_encryption_key=Fernet.generate_key().decode(),
    )
    return AuthVerifier(settings)


def _timestamps(seconds: int = 180) -> dict[str, int | str]:
    now = int(time.time())
    return {
        "iss": "https://auth.ithute.co.ls",
        "aud": "ithute-push",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + seconds,
    }


def test_push_user_token_requires_dedicated_scope_session_and_claim_shape() -> None:
    verifier = _verifier()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    good = {
        **_timestamps(),
        "token_use": "push_access",
        "azp": "ithute-tutor",
        "scope": "push.device",
        "sub": str(user_id),
        "sid": str(session_id),
    }
    verifier._decode = lambda token, required: good
    principal = verifier.user("ignored")
    assert principal.sub == str(user_id)
    assert principal.client_id == "ithute-tutor"
    assert principal.session_id == str(session_id)

    wrong_type = {**good, "token_use": "access"}
    verifier._decode = lambda token, required: wrong_type
    with pytest.raises(AuthError):
        verifier.user("ignored")

    wrong_subject = {**good, "sub": "not-a-uuid"}
    verifier._decode = lambda token, required: wrong_subject
    with pytest.raises(AuthError):
        verifier.user("ignored")


def test_push_user_token_lifetime_is_capped() -> None:
    verifier = _verifier()
    claims = {
        **_timestamps(seconds=601),
        "token_use": "push_access",
        "azp": "ithute-tutor",
        "scope": "push.device",
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
    }
    verifier._decode = lambda token, required: claims
    with pytest.raises(AuthError, match="lifetime"):
        verifier.user("ignored")


def test_service_subject_must_match_authorized_party() -> None:
    verifier = _verifier()
    claims = {
        **_timestamps(seconds=300),
        "token_use": "service",
        "azp": "ithute-tutor",
        "scope": "push.send",
        "sub": "service:loanhub",
    }
    verifier._decode = lambda token, required: claims
    with pytest.raises(AuthError, match="subject"):
        verifier.service("ignored")


def test_lifecycle_token_is_separate_from_product_service_token() -> None:
    verifier = _verifier()
    claims = {
        **_timestamps(seconds=300),
        "token_use": "service",
        "sub": "service:ithute-auth",
        "azp": "ithute-auth",
        "scope": "push.lifecycle",
    }
    verifier._decode = lambda token, required: claims
    assert verifier.lifecycle("ignored").client_id == "ithute-auth"
    with pytest.raises(AuthError):
        verifier.service("ignored")


def test_lifecycle_schema_rejects_ambiguous_or_future_events() -> None:
    with pytest.raises(ValidationError):
        AuthLifecycleEventRequest(
            event_id=uuid.uuid4(),
            type="account.disabled",
            sub=uuid.uuid4(),
            client_id="ithute-tutor",
            occurred_at=datetime.now(timezone.utc),
        )

    with pytest.raises(ValidationError):
        AuthLifecycleEventRequest(
            event_id=uuid.uuid4(),
            type="application.disabled",
            client_id="ithute-tutor",
            occurred_at=datetime.now(timezone.utc) + timedelta(minutes=6),
        )


def test_lifecycle_timestamps_round_trip_as_aware_utc() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    user_id = uuid.uuid4()
    event_id = uuid.uuid4()
    occurred_at = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add(
            AuthLifecycleEvent(
                event_id=event_id,
                event_type="account.disabled",
                auth_user_id=user_id,
                occurred_at=occurred_at,
                details_json="{}",
            )
        )
        db.commit()
        db.expire_all()
        stored = db.get(AuthLifecycleEvent, event_id)
        assert stored is not None
        assert stored.occurred_at.tzinfo is not None
        assert stored.occurred_at.utcoffset() == timedelta(0)


def test_stale_status_event_cannot_roll_state_backwards() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    user_id = uuid.uuid4()
    t0 = datetime.now(timezone.utc)
    with Session(engine) as db:
        disabled = AuthLifecycleEventRequest(
            event_id=uuid.uuid4(),
            type="account.disabled",
            sub=user_id,
            occurred_at=t0 + timedelta(seconds=10),
        )
        result = apply_auth_event(disabled, LifecyclePrincipal(), db)
        assert result.applied is True
        assert db.get(AuthUserState, user_id).active is False

        enabled = AuthLifecycleEventRequest(
            event_id=uuid.uuid4(),
            type="account.enabled",
            sub=user_id,
            occurred_at=t0 + timedelta(seconds=20),
        )
        result = apply_auth_event(enabled, LifecyclePrincipal(), db)
        assert result.applied is True
        assert db.get(AuthUserState, user_id).active is True

        stale_disable = AuthLifecycleEventRequest(
            event_id=uuid.uuid4(),
            type="account.disabled",
            sub=user_id,
            occurred_at=t0 + timedelta(seconds=5),
        )
        result = apply_auth_event(stale_disable, LifecyclePrincipal(), db)
        assert result.applied is False
        assert db.get(AuthUserState, user_id).active is True


def test_application_state_ordering_uses_same_utc_rules() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    t0 = datetime.now(timezone.utc)
    with Session(engine) as db:
        disabled = AuthLifecycleEventRequest(
            event_id=uuid.uuid4(),
            type="application.disabled",
            client_id="ithute-tutor",
            occurred_at=t0 + timedelta(seconds=10),
        )
        assert apply_auth_event(disabled, LifecyclePrincipal(), db).applied is True
        assert db.get(ApplicationState, "ithute-tutor").active is False

        enabled = AuthLifecycleEventRequest(
            event_id=uuid.uuid4(),
            type="application.enabled",
            client_id="ithute-tutor",
            occurred_at=t0 + timedelta(seconds=20),
        )
        assert apply_auth_event(enabled, LifecyclePrincipal(), db).applied is True
        assert db.get(ApplicationState, "ithute-tutor").active is True

        stale_disable = AuthLifecycleEventRequest(
            event_id=uuid.uuid4(),
            type="application.disabled",
            client_id="ithute-tutor",
            occurred_at=t0 + timedelta(seconds=5),
        )
        assert apply_auth_event(stale_disable, LifecyclePrincipal(), db).applied is False
        assert db.get(ApplicationState, "ithute-tutor").active is True


def test_revoked_session_is_rejected_even_with_unexpired_token() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    with Session(engine) as db:
        db.add(
            RevokedAuthSession(
                session_id=session_id,
                auth_user_id=user_id,
                application_id="ithute-tutor",
                revoked_at=datetime.now(timezone.utc),
                event_id=uuid.uuid4(),
            )
        )
        db.commit()
        principal = UserPrincipal(
            sub=str(user_id),
            client_id="ithute-tutor",
            session_id=str(session_id),
        )
        with pytest.raises(HTTPException) as exc:
            require_live_user_state(db, principal)
        assert exc.value.status_code == 401
