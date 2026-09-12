from pathlib import Path

from app.api.v1.external_webmail import ExternalLogin
from app.api.v1.external_webmail_smart import _provider_adjusted_login
from app.services.mail_migration import _folder_pair, _write_maildir_message
from app.services.mail_provider_detection import detect_mail_provider, provider_detection_payload


def test_gmail_address_detects_google_without_dns():
    profile = detect_mail_provider("Person@GMAIL.com")
    assert profile is not None
    assert profile.key == "google"
    assert profile.imap_host == "imap.gmail.com"
    assert profile.imap_port == 993
    assert profile.smtp_host == "smtp.gmail.com"
    assert profile.smtp_port == 587
    assert profile.auth_mode == "oauth_preferred"


def test_outlook_address_detects_microsoft_without_dns():
    profile = detect_mail_provider("person@outlook.com")
    assert profile is not None
    assert profile.key == "microsoft365"
    assert profile.imap_host == "outlook.office365.com"


def test_provider_payload_exposes_gmail_secure_defaults():
    result = provider_detection_payload("user@gmail.com")
    assert result["detected"] is True
    assert result["provider"]["key"] == "google"
    assert result["provider"]["imap_security"] == "ssl"
    assert result["provider"]["smtp_security"] == "starttls"


def test_smart_login_replaces_generated_gmail_hosts():
    payload = ExternalLogin(
        address="user@gmail.com",
        password="app-password",
        username="",
        imap_host="mail.gmail.com",
        imap_port=993,
        imap_security="ssl",
        smtp_host="mail.gmail.com",
        smtp_port=465,
        smtp_security="ssl",
    )
    adjusted, detection = _provider_adjusted_login(payload)
    assert detection["provider"]["key"] == "google"
    assert adjusted.username == "user@gmail.com"
    assert adjusted.imap_host == "imap.gmail.com"
    assert adjusted.imap_port == 993
    assert adjusted.smtp_host == "smtp.gmail.com"
    assert adjusted.smtp_port == 587
    assert adjusted.smtp_security == "starttls"


def test_smart_login_preserves_explicit_manual_hosts():
    payload = ExternalLogin(
        address="user@gmail.com",
        password="app-password",
        username="custom-user",
        imap_host="imap.example.net",
        imap_port=993,
        imap_security="ssl",
        smtp_host="smtp.example.net",
        smtp_port=587,
        smtp_security="starttls",
    )
    adjusted, _ = _provider_adjusted_login(payload)
    assert adjusted.imap_host == "imap.example.net"
    assert adjusted.smtp_host == "smtp.example.net"
    assert adjusted.username == "custom-user"


def test_gmail_special_folder_keeps_source_name_and_safe_destination():
    source, destination = _folder_pair(b'(\\HasNoChildren) "/" "[Gmail]/All Mail"')
    assert source == "[Gmail]/All Mail"
    assert destination == "_Gmail_.All Mail"


def test_migration_write_is_idempotent_and_preserves_flags(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.mail_migration.os.chown", lambda *_args, **_kwargs: None)
    target = tmp_path / "Maildir"
    raw = b"From: sender@example.com\r\nTo: user@example.com\r\nSubject: Test\r\n\r\nHello"
    meta = b"1 (FLAGS (\\Seen \\Flagged))"

    assert _write_maildir_message(target, raw, meta) is True
    assert _write_maildir_message(target, raw, meta) is False

    imported = list((target / "cur").glob("migrated.*.migration:2,*"))
    assert len(imported) == 1
    assert imported[0].name.endswith(":2,FS")
