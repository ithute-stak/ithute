from pathlib import Path

from app.models.mail import Mailbox, MailboxStatus
from app.services.mail_account_sync import MailAccountSyncError, sync_mailbox


def _mailbox(address: str, password_hash: str, status: MailboxStatus = MailboxStatus.active) -> Mailbox:
    local, _domain = address.split("@", 1)
    return Mailbox(
        address=address,
        local_part=local,
        password_hash=password_hash,
        status=status,
        quota_bytes=5 * 1024**3,
    )


def test_sync_replaces_only_matching_account_and_preserves_external_accounts(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "info@ithute.co.ls|{SHA512-CRYPT}$6$old$hash\n"
        "info@external.example|{SHA512-CRYPT}$6$external$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))

    mailbox = _mailbox("info@ithute.co.ls", "{SHA512-CRYPT}$6$new$hash")
    assert sync_mailbox(mailbox) is True

    content = account_file.read_text(encoding="utf-8")
    assert "info@ithute.co.ls|{SHA512-CRYPT}$6$new$hash" in content
    assert "info@ithute.co.ls|{SHA512-CRYPT}$6$old$hash" not in content
    assert "info@external.example|{SHA512-CRYPT}$6$external$hash" in content
    assert account_file.stat().st_mode & 0o777 == 0o600


def test_sync_removes_suspended_account(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "info@ithute.co.ls|{SHA512-CRYPT}$6$current$hash\n"
        "other@example.com|{SHA512-CRYPT}$6$other$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))

    mailbox = _mailbox(
        "info@ithute.co.ls",
        "{SHA512-CRYPT}$6$current$hash",
        status=MailboxStatus.suspended,
    )
    sync_mailbox(mailbox)

    content = account_file.read_text(encoding="utf-8")
    assert "info@ithute.co.ls|" not in content
    assert "other@example.com|{SHA512-CRYPT}$6$other$hash" in content


def test_sync_rejects_unsupported_hash(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(tmp_path / "postfix-accounts.cf"))
    mailbox = _mailbox("info@ithute.co.ls", "not-a-mail-hash")

    try:
        sync_mailbox(mailbox)
    except MailAccountSyncError as exc:
        assert "SHA512-CRYPT" in str(exc)
    else:
        raise AssertionError("unsupported hash was accepted")


def test_sync_is_disabled_without_runtime_account_file(monkeypatch):
    monkeypatch.delenv("MAIL_ACCOUNTS_FILE", raising=False)
    mailbox = _mailbox("info@ithute.co.ls", "{SHA512-CRYPT}$6$current$hash")
    assert sync_mailbox(mailbox) is False
