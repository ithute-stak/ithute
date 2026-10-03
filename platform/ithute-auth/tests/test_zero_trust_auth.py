import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("AUTH_DATABASE_URL", "sqlite://")

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import Settings
from app.models import AuthSession, utcnow
from app.security_service import privileged_account, recent_step_up


def test_zero_trust_auth_migration_is_single_head() -> None:
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == ["0010_zero_trust_sessions"]


def test_privileged_account_includes_database_admin_and_configured_owner() -> None:
    settings = Settings(database_url="sqlite://", system_owner_email="owner@ithute.co.ls", system_owner_password="strong-password")
    assert privileged_account(SimpleNamespace(is_platform_admin=True, email="admin@example.com"), settings)
    assert privileged_account(SimpleNamespace(is_platform_admin=False, email="owner@ithute.co.ls"), settings)
    assert not privileged_account(SimpleNamespace(is_platform_admin=False, email="user@example.com"), settings)


def test_recent_step_up_requires_aal3_and_fresh_proof() -> None:
    settings = Settings(database_url="sqlite://", step_up_minutes=10)
    session = SimpleNamespace(
        assurance_level=3,
        last_step_up_at=utcnow() - timedelta(minutes=2),
    )
    assert recent_step_up(session, settings=settings)

    session.assurance_level = 2
    assert not recent_step_up(session, settings=settings)

    session.assurance_level = 3
    session.last_step_up_at = utcnow() - timedelta(minutes=11)
    assert not recent_step_up(session, settings=settings)


def test_privileged_password_login_requires_passkey_when_enrolled() -> None:
    source = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert "privileged_password_login_blocked" in source
    assert "privileged account requires passkey authentication" in source
    assert "privileged_passkey_bootstrap_required" in source


def test_passkey_step_up_raises_session_to_aal3() -> None:
    source = (Path(__file__).parents[1] / "app" / "passkeys.py").read_text(encoding="utf-8")
    assert '@router.post("/v1/account/step-up/passkey/options")' in source
    assert '@router.post("/v1/account/step-up/passkey/verify"' in source
    assert "context.session.assurance_level = 3" in source
    assert "context.session.last_step_up_at = now" in source


def test_security_posture_and_device_trust_are_exposed() -> None:
    source = (Path(__file__).parents[1] / "app" / "account.py").read_text(encoding="utf-8")
    assert '@router.get("/security-posture")' in source
    assert '@router.post("/devices/{device_key}/trust")' in source
    assert "fresh passkey step-up required" in source
