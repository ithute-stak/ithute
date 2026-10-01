import pytest

from app.services import caddy_routes
from app.services.caddy_routes import CaddyRouteError


def test_render_route_accepts_public_http_origin():
    rendered = caddy_routes.render_route("app.example.com", "http://203.0.113.10:8080")
    assert "app.example.com {" in rendered
    assert "reverse_proxy http://203.0.113.10:8080" in rendered
    assert "Strict-Transport-Security" in rendered


def test_render_route_rejects_direct_private_origin():
    with pytest.raises(CaddyRouteError):
        caddy_routes.render_route("app.example.com", "http://127.0.0.1:8080")
    with pytest.raises(CaddyRouteError):
        caddy_routes.render_route("app.example.com", "http://169.254.169.254:80")


def test_render_route_rejects_caddy_injection_hostname():
    with pytest.raises(CaddyRouteError):
        caddy_routes.render_route("example.com { respond hacked }", "https://203.0.113.10")


def test_propagation_requires_expected_edge_ip(monkeypatch):
    monkeypatch.setattr(caddy_routes, "expected_edge_ips", lambda: {"203.0.113.20"})
    monkeypatch.setattr(caddy_routes, "resolve_hostname_ips", lambda _hostname: {"203.0.113.9"})
    pending = caddy_routes.propagation_state("app.example.com")
    assert pending["propagated"] is False

    monkeypatch.setattr(caddy_routes, "resolve_hostname_ips", lambda _hostname: {"203.0.113.9", "203.0.113.20"})
    ready = caddy_routes.propagation_state("app.example.com")
    assert ready["propagated"] is True
    assert ready["expected_ips"] == ["203.0.113.20"]
