from types import SimpleNamespace

from app.api.v1.ithute_auth import _safe_next_path
from app.core.config import settings
from app.services.platform_mode import effective_platform_mode


class _ScalarSession:
    def __init__(self, row):
        self.row = row

    def scalar(self, _statement):
        return self.row


def test_domain_deployment_reconciles_only_stale_bootstrap_row(monkeypatch) -> None:
    monkeypatch.setattr(settings, "platform_mode", "domain")

    assert effective_platform_mode(_ScalarSession(SimpleNamespace(mode="bootstrap"))) == "domain_active"
    assert effective_platform_mode(_ScalarSession(None)) == "domain_active"

    # A real setup transition remains authoritative and must not be skipped.
    assert effective_platform_mode(_ScalarSession(SimpleNamespace(mode="domain_pending"))) == "domain_pending"
    assert effective_platform_mode(_ScalarSession(SimpleNamespace(mode="domain_verified"))) == "domain_verified"
    assert effective_platform_mode(_ScalarSession(SimpleNamespace(mode="domain_active"))) == "domain_active"


def test_bootstrap_deployment_remains_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "platform_mode", "bootstrap")
    assert effective_platform_mode(_ScalarSession(SimpleNamespace(mode="bootstrap"))) == "bootstrap"
    assert effective_platform_mode(_ScalarSession(None)) == "bootstrap"


def test_sso_next_path_is_application_local_only() -> None:
    assert _safe_next_path(None) == "/dashboard"
    assert _safe_next_path("") == "/dashboard"
    assert _safe_next_path("/dashboard") == "/dashboard"
    assert _safe_next_path("/hosting-builds?project=abc") == "/hosting-builds?project=abc"

    assert _safe_next_path("https://evil.example/steal") == "/dashboard"
    assert _safe_next_path("//evil.example/steal") == "/dashboard"
    assert _safe_next_path("/\\evil.example") == "/dashboard"
    assert _safe_next_path("dashboard") == "/dashboard"
