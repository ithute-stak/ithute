from datetime import datetime, timezone

import pytest

from app.api.v1.external_webmail_smart import _status_parts
from app.services import mail_migration


def test_internaldate_is_preserved_and_repeat_write_is_deduplicated(tmp_path, monkeypatch):
    monkeypatch.setattr(mail_migration.os, "chown", lambda *_args, **_kwargs: None)
    raw = b"From: old@example.com\r\nTo: new@example.com\r\nSubject: preserved\r\n\r\nhello"
    meta = b'1 (UID 77 FLAGS (\\Seen \\Flagged) INTERNALDATE "14-Feb-2025 12:34:56 +0200")'
    timestamp = mail_migration._internaldate_timestamp(meta)

    assert timestamp == datetime(2025, 2, 14, 10, 34, 56, tzinfo=timezone.utc).timestamp()
    assert mail_migration._write_maildir_message(tmp_path, raw, meta, timestamp) is True
    assert mail_migration._write_maildir_message(tmp_path, raw, meta, timestamp) is False

    files = list((tmp_path / "cur").iterdir())
    assert len(files) == 1
    assert ":2,FS" in files[0].name
    assert abs(files[0].stat().st_mtime - timestamp) < 1
    assert files[0].read_bytes() == raw


def test_plaintext_source_imap_is_rejected(monkeypatch):
    monkeypatch.setattr(mail_migration, "_assert_public_host", lambda *_args: None)
    with pytest.raises(ValueError, match="ssl or starttls"):
        mail_migration._open_source_client("mail.example.com", 143, "plain")


def test_private_source_guard_runs_before_imap_connection(monkeypatch):
    class Blocked(ValueError):
        pass

    monkeypatch.setattr(mail_migration, "_assert_public_host", lambda *_args: (_ for _ in ()).throw(Blocked("private target")))
    monkeypatch.setattr(mail_migration.imaplib, "IMAP4_SSL", lambda *_args, **_kwargs: pytest.fail("connection must not be attempted"))

    with pytest.raises(Blocked, match="private target"):
        mail_migration._open_source_client("127.0.0.1", 993, "ssl")


def test_legacy_and_phased_job_statuses_are_read_compatibly():
    assert _status_parts("completed") == ("completed", "initial")
    assert _status_parts("queued_delta") == ("queued", "delta")
    assert _status_parts("partial_final") == ("partial", "final")
