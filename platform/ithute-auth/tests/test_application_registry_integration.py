"""Integration regression: database-managed callback URL is authoritative."""
import os
from types import SimpleNamespace

os.environ.setdefault("AUTH_DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Application, ApplicationRedirectURI
from app.application_registry import register_application, replace_redirect_uris
from app.oauth import _require_client_redirect


def test_registered_nextjs_app_can_only_use_dashboard_callback():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    registered = "https://capitalbridge.example.com/api/auth/ithute/callback"
    unsafe = "https://attacker.example.com/api/auth/ithute/callback"
    with Session(engine) as db:
        app = register_application(db, client_id="capitalbridge-nextjs", name="CapitalBridge", redirect_uris=[registered])
        assert app.is_active is False
        db.commit()

        config = SimpleNamespace(redirect_uris={"capitalbridge-nextjs": (unsafe,)})
        with pytest.raises(HTTPException) as denied:
            _require_client_redirect(db, config, "capitalbridge-nextjs", registered)
        assert denied.value.detail == "invalid_client"

        app.is_active = True
        db.commit()
        assert _require_client_redirect(db, config, "capitalbridge-nextjs", registered).client_id == "capitalbridge-nextjs"

        with pytest.raises(HTTPException) as denied:
            _require_client_redirect(db, config, "capitalbridge-nextjs", unsafe)
        assert denied.value.detail == "invalid_redirect_uri"

        replacement = "https://capitalbridge.example.com/auth/callback"
        replace_redirect_uris(db, application=app, redirect_uris=[replacement])
        db.commit()
        assert _require_client_redirect(db, config, "capitalbridge-nextjs", replacement).id == app.id
        with pytest.raises(HTTPException):
            _require_client_redirect(db, config, "capitalbridge-nextjs", registered)
    engine.dispose()
