import imaplib
import ssl

import pytest

from app.services import webmail


class FakeImap:
    def __init__(self):
        self.starttls_calls = 0
        self.login_calls = []
        self.logout_calls = 0

    def starttls(self, *, ssl_context):
        assert isinstance(ssl_context, ssl.SSLContext)
        self.starttls_calls += 1
        return "OK", []

    def login(self, address, password):
        self.login_calls.append((address, password))
        return "OK", []

    def logout(self):
        self.logout_calls += 1
        return "BYE", []


def test_port_993_uses_implicit_tls(monkeypatch):
    client = FakeImap()
    ssl_calls = []

    def fake_ssl(host, port, *, ssl_context, timeout):
        ssl_calls.append((host, port, ssl_context, timeout))
        return client

    def fail_plain(*args, **kwargs):
        raise AssertionError("port 993 must not use plain IMAP plus STARTTLS")

    monkeypatch.setattr(webmail.settings, "webmail_imap_host", "mail.ithute.co.ls")
    monkeypatch.setattr(webmail.settings, "webmail_imap_port", 993)
    monkeypatch.setattr(webmail.imaplib, "IMAP4_SSL", fake_ssl)
    monkeypatch.setattr(webmail.imaplib, "IMAP4", fail_plain)

    connected = webmail._imap("person@example.com", "correct-password")

    assert connected is client
    assert len(ssl_calls) == 1
    assert client.starttls_calls == 0
    assert client.login_calls == [("person@example.com", "correct-password")]


def test_port_143_uses_starttls(monkeypatch):
    client = FakeImap()
    plain_calls = []

    def fake_plain(host, port, *, timeout):
        plain_calls.append((host, port, timeout))
        return client

    def fail_ssl(*args, **kwargs):
        raise AssertionError("port 143 must negotiate STARTTLS, not implicit TLS")

    monkeypatch.setattr(webmail.settings, "webmail_imap_host", "dovecot")
    monkeypatch.setattr(webmail.settings, "webmail_imap_port", 143)
    monkeypatch.setattr(webmail.imaplib, "IMAP4", fake_plain)
    monkeypatch.setattr(webmail.imaplib, "IMAP4_SSL", fail_ssl)

    connected = webmail._imap("person@example.com", "correct-password")

    assert connected is client
    assert len(plain_calls) == 1
    assert client.starttls_calls == 1
    assert client.login_calls == [("person@example.com", "correct-password")]


def test_auth_failure_is_not_reported_as_transport_failure(monkeypatch):
    class RejectingImap(FakeImap):
        def login(self, address, password):
            raise imaplib.IMAP4.error("authentication failed")

    client = RejectingImap()
    monkeypatch.setattr(webmail.settings, "webmail_imap_port", 993)
    monkeypatch.setattr(webmail.imaplib, "IMAP4_SSL", lambda *args, **kwargs: client)

    with pytest.raises(webmail.WebmailError, match="Mailbox address or password was not accepted"):
        webmail._imap("person@example.com", "wrong-password")

    assert client.logout_calls == 1


def test_connection_failure_is_not_reported_as_bad_password(monkeypatch):
    monkeypatch.setattr(webmail.settings, "webmail_imap_port", 993)

    def fail_connect(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(webmail.imaplib, "IMAP4_SSL", fail_connect)

    with pytest.raises(webmail.WebmailError, match="Mail server connection failed"):
        webmail._imap("person@example.com", "correct-password")


def test_production_tls_verifies_certificates(monkeypatch):
    monkeypatch.setattr(webmail.settings, "environment", "production")
    context = webmail._tls_context()
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
