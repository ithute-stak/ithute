import pytest

from app.services.platform_setup import (
    bootstrap_caddyfile,
    hardened_caddyfile,
    normalize_platform_domain,
    platform_names,
    validate_public_ip,
)


def test_platform_domain_normalization_and_hostnames():
    assert normalize_platform_domain(" Example.CO.LS. ") == "example.co.ls"
    names = platform_names("example.co.ls")
    assert names.panel == "panel.example.co.ls"
    assert names.api == "api.example.co.ls"
    assert names.groupware == "groupware.example.co.ls"
    assert names.mail == "mail.example.co.ls"
    assert names.ns1 == "ns1.example.co.ls"
    assert names.ns2 == "ns2.example.co.ls"


def test_platform_domain_rejects_ip_address():
    with pytest.raises(ValueError, match="DNS name"):
        normalize_platform_domain("1.1.1.1")


def test_public_ip_validation_rejects_private_address():
    assert validate_public_ip("1.1.1.1") == "1.1.1.1"
    with pytest.raises(ValueError, match="globally routable"):
        validate_public_ip("10.0.0.10")


def test_bootstrap_caddyfile_serves_panel_and_api_on_raw_ip():
    config = bootstrap_caddyfile("1.1.1.1")
    assert "admin 0.0.0.0:2019" in config
    assert "http://1.1.1.1" in config
    assert "@api path /api/*" in config
    assert "reverse_proxy backend:8000" in config
    assert "reverse_proxy frontend:3000" in config
    assert "Strict-Transport-Security" not in config


def test_hardened_caddyfile_redirects_ip_and_enables_https_security():
    names = platform_names("example.co.ls")
    config = hardened_caddyfile(names, "1.1.1.1", "ops@example.co.ls")
    assert "redir https://panel.example.co.ls{uri} permanent" in config
    assert "panel.example.co.ls" in config
    assert "api.example.co.ls" in config
    assert "groupware.example.co.ls" in config
    assert "Strict-Transport-Security" in config
    assert "reverse_proxy radicale:5232" in config


def test_hardened_caddyfile_requires_valid_acme_email():
    names = platform_names("example.co.ls")
    with pytest.raises(ValueError, match="ACME"):
        hardened_caddyfile(names, "1.1.1.1", "not-an-email")
