import os
from types import SimpleNamespace

os.environ.setdefault("AUTH_DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Base
from app.models import AuditEvent
from app.security_service import client_ip, login_rate_limited


TRUSTED_TEST_PROXY_CIDRS = "10.0.0.0/8"


def _request(forwarded: str | None = None):
    headers = {}
    if forwarded is not None:
        headers["x-forwarded-for"] = forwarded
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host="10.0.0.5"))


def test_client_ip_uses_edge_appended_forwarded_address() -> None:
    request = _request("203.0.113.10, 198.51.100.22")
    settings = Settings(
        database_url="sqlite://",
        trusted_proxy_cidrs=TRUSTED_TEST_PROXY_CIDRS,
    )
    assert client_ip(request, settings) == "198.51.100.22"


def test_untrusted_peer_cannot_spoof_forwarded_address() -> None:
    request = _request("198.51.100.22")
    settings = Settings(
        database_url="sqlite://",
        trusted_proxy_cidrs="127.0.0.1/32,::1/128",
    )
    assert client_ip(request, settings) == "10.0.0.5"


def test_login_rate_limit_counts_recent_failed_auth_events() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite://",
        login_rate_max_failures_per_ip=3,
        login_rate_window_seconds=900,
        trusted_proxy_cidrs=TRUSTED_TEST_PROXY_CIDRS,
    )
    request = _request("198.51.100.22")

    with Session(engine) as db:
        for event_type in ("login_failed", "oidc_login_failed", "mfa_challenge_failed"):
            db.add(
                AuditEvent(
                    event_type=event_type,
                    success=False,
                    ip_address="198.51.100.22",
                )
            )
        db.commit()
        assert login_rate_limited(db, request=request, settings=settings) is True


def test_successful_or_other_ip_events_do_not_trigger_limit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite://",
        login_rate_max_failures_per_ip=2,
        login_rate_window_seconds=900,
        trusted_proxy_cidrs=TRUSTED_TEST_PROXY_CIDRS,
    )
    request = _request("198.51.100.22")

    with Session(engine) as db:
        db.add(AuditEvent(event_type="login_failed", success=False, ip_address="203.0.113.99"))
        db.add(AuditEvent(event_type="login_succeeded", success=True, ip_address="198.51.100.22"))
        db.commit()
        assert login_rate_limited(db, request=request, settings=settings) is False
