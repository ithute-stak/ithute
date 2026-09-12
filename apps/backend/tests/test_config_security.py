import pytest
from pydantic import ValidationError

from app.core.config import Settings


def base_kwargs():
    return {
        "database_url": "postgresql+psycopg://user:password@postgres:5432/test",
        "redis_url": "redis://redis:6379/0",
        "frontend_url": "http://203.0.113.10",
        "bootstrap_admin_email": "owner@example.test",
    }


def prod_kwargs():
    return {
        "platform_mode": "bootstrap",
        "bootstrap_public_ip": "1.1.1.1",
        "nameserver_1": "ns1.mail.example.org",
        "nameserver_2": "ns2.mail.example.org",
        "powerdns_api_key": "5e2f1f60c31749d5ad1695f25c386f37",
        "mail_hostname": "mail.example.org",
        "mail_public_ip": "1.1.1.1",
        "mail_ops_token": "f01cb489689f42a68fd35c78d8c6bd8f",
        "recovery_ops_token": "3dcf8e5467a64dffb53a77d63a8817f2",
        "mail_node_token": "73944eaac84246b99f0723f302d2bf86",
        "mail_tls_mode": "selfsigned",
        "dkim_encryption_key": "1f49c08e7bf14949ae69f7966f03d934d7583292",
        "billing_webhook_secret": "ce93d97536e14a22ad78f31c0a58e178d457f1e4",
        "rspamd_redis_url": "redis://rspamd-redis:6379/0",
        "groupware_public_url": "http://203.0.113.10:5232",
    }


def domain_kwargs():
    values = prod_kwargs()
    values.update(
        {
            "platform_mode": "domain",
            "mail_tls_mode": "acme",
            "system_email_from": "no-reply@example.org",
            "system_smtp_host": "smtp.example.org",
            "groupware_public_url": "https://groupware.example.org",
        }
    )
    return values


def make_settings(*, values=None, cookie_secure=False, **overrides):
    kwargs = dict(prod_kwargs() if values is None else values)
    kwargs.update(overrides)
    return Settings(
        **base_kwargs(),
        **kwargs,
        environment="production",
        cookie_secure=cookie_secure,
        secret_key="7afcc49630d64dfb9226dcf91db29d106314b5c6",
        bootstrap_admin_password="Nf8!7wMm3pQ4xL2z",
    )


def test_rejects_short_secret_key():
    with pytest.raises(ValidationError):
        Settings(**base_kwargs(), secret_key="too-short", bootstrap_admin_password="StrongPassword!123")


def test_rejects_short_dkim_encryption_key():
    with pytest.raises(ValidationError):
        Settings(
            **base_kwargs(),
            secret_key="7afcc49630d64dfb9226dcf91db29d106314b5c6",
            dkim_encryption_key="too-short",
            bootstrap_admin_password="StrongPassword!123",
        )


def test_production_rejects_placeholder_secret():
    with pytest.raises(ValidationError):
        Settings(
            **base_kwargs(),
            **prod_kwargs(),
            environment="production",
            cookie_secure=False,
            secret_key="development-only-secret-key-change-me-1234",
            bootstrap_admin_password="StrongPassword!123",
        )


def test_production_rejects_missing_dedicated_dkim_key():
    values = prod_kwargs()
    values.pop("dkim_encryption_key")
    with pytest.raises(ValidationError):
        make_settings(values=values)


def test_production_rejects_dkim_key_equal_to_app_secret():
    secret = "7afcc49630d64dfb9226dcf91db29d106314b5c6"
    values = prod_kwargs()
    values["dkim_encryption_key"] = secret
    with pytest.raises(ValidationError):
        Settings(
            **base_kwargs(),
            **values,
            environment="production",
            cookie_secure=False,
            secret_key=secret,
            bootstrap_admin_password="Nf8!7wMm3pQ4xL2z",
        )


def test_production_requires_global_bootstrap_ip():
    values = prod_kwargs()
    values.pop("bootstrap_public_ip")
    with pytest.raises(ValidationError):
        make_settings(values=values)

    values = prod_kwargs()
    values["bootstrap_public_ip"] = "10.0.0.10"
    with pytest.raises(ValidationError):
        make_settings(values=values)


def test_bootstrap_mode_allows_http_cookie_bootstrap_and_self_signed_mail_tls():
    settings = make_settings(cookie_secure=False)
    assert settings.platform_mode == "bootstrap"
    assert settings.cookie_secure is False
    assert settings.mail_tls_mode == "selfsigned"
    assert settings.bootstrap_public_ip == "1.1.1.1"


def test_domain_mode_requires_secure_cookies():
    with pytest.raises(ValidationError):
        make_settings(values=domain_kwargs(), cookie_secure=False)


def test_domain_mode_rejects_placeholder_nameservers():
    values = domain_kwargs()
    values["nameserver_1"] = "ns1.mailbox-dns.example"
    values["nameserver_2"] = "ns2.mailbox-dns.example"
    with pytest.raises(ValidationError):
        make_settings(values=values, cookie_secure=True)


def test_domain_mode_rejects_placeholder_mail_hostname():
    values = domain_kwargs()
    values["mail_hostname"] = "mail.phase7.test"
    with pytest.raises(ValidationError):
        make_settings(values=values, cookie_secure=True)


def test_production_rejects_missing_public_mail_ip():
    values = prod_kwargs()
    values.pop("mail_public_ip")
    with pytest.raises(ValidationError):
        make_settings(values=values)


def test_production_rejects_private_mail_ip():
    values = prod_kwargs()
    values["mail_public_ip"] = "10.0.0.10"
    with pytest.raises(ValidationError):
        make_settings(values=values)


def test_production_rejects_placeholder_mail_ops_token():
    values = prod_kwargs()
    values["mail_ops_token"] = "development-mail-ops-token-change-me"
    with pytest.raises(ValidationError):
        make_settings(values=values)


def test_domain_mode_rejects_self_signed_mail_tls():
    values = domain_kwargs()
    values["mail_tls_mode"] = "selfsigned"
    with pytest.raises(ValidationError):
        make_settings(values=values, cookie_secure=True)


def test_domain_mode_requires_system_email_delivery():
    values = domain_kwargs()
    values["system_smtp_host"] = None
    with pytest.raises(ValidationError):
        make_settings(values=values, cookie_secure=True)


def test_domain_mode_rejects_system_smtp_without_tls():
    values = domain_kwargs()
    values["system_smtp_ssl"] = False
    values["system_smtp_starttls"] = False
    with pytest.raises(ValidationError):
        make_settings(values=values, cookie_secure=True)


def test_production_accepts_non_placeholder_bootstrap_configuration():
    settings = make_settings(cookie_secure=False)
    assert settings.environment == "production"
    assert settings.platform_mode == "bootstrap"
    assert settings.mail_hostname == "mail.example.org"
    assert settings.mail_public_ip == "1.1.1.1"
    assert settings.dkim_encryption_key != settings.secret_key
    assert settings.billing_webhook_secret


def test_production_accepts_hardened_domain_configuration():
    settings = make_settings(values=domain_kwargs(), cookie_secure=True)
    assert settings.platform_mode == "domain"
    assert settings.cookie_secure is True
    assert settings.mail_tls_mode == "acme"
    assert settings.groupware_public_url.startswith("https://")
