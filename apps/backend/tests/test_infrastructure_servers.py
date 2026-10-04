from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1.infrastructure_servers import _fresh, _hostname, _roles


def test_infrastructure_server_role_validation_and_hostname_normalization():
    assert _hostname("VPS01.Ithute.CO.LS.") == "vps01.ithute.co.ls"
    assert _roles(["database", "mail", "mail"]) == ["database", "mail"]

    with pytest.raises(HTTPException):
        _roles(["mail", "root-shell"])


def test_infrastructure_server_heartbeat_freshness():
    now = datetime.now(timezone.utc)
    assert _fresh(now - timedelta(seconds=30)) is True
    assert _fresh(now - timedelta(minutes=10)) is False
    assert _fresh(None) is False


def test_infrastructure_server_contract_and_navigation_exist():
    root = Path(__file__).parents[2]
    api_source = (root / "app" / "api" / "v1" / "infrastructure_servers.py").read_text(encoding="utf-8")
    model_source = (root / "app" / "models" / "infrastructure.py").read_text(encoding="utf-8")
    ui_root = root.parent / "frontend"
    page_source = (ui_root / "app" / "infrastructure" / "servers" / "page.tsx").read_text(encoding="utf-8")
    nav_source = (ui_root / "components" / "control-shell.tsx").read_text(encoding="utf-8")

    assert 'prefix="/platform/infrastructure"' in api_source
    assert '@router.get("/servers")' in api_source
    assert '@router.post("/servers/import-existing")' in api_source
    assert '@router.patch("/servers/{server_id}")' in api_source
    assert 'class InfrastructureServer' in model_source
    assert 'Servers & VPS nodes' in nav_source
    assert '/infrastructure/servers' in nav_source
    assert 'Synchronize existing nodes' in page_source
    assert 'Mail role' in page_source
    assert 'Hosting & databases' in page_source
