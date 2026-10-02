from pathlib import Path

from app.models.mail import Mailbox, MailboxStatus
from app.services.mail_account_sync import MailAccountSyncError, sync_mailbox, sync_mailbox_forwarding


def _mailbox(address: str, password_hash: str, status: MailboxStatus = MailboxStatus.active) -> Mailbox:
    local, _domain = address.split("@", 1)
    return Mailbox(
        address=address,
        local_part=local,
        password_hash=password_hash,
        status=status,
        quota_bytes=5 * 1024**3,
    )


def _enable_forwarding_runtime(tmp_path: Path) -> None:
    (tmp_path / ".recipient-bcc-ready").write_text("ready\n", encoding="utf-8")


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




def test_sync_preserves_account_file_inode_for_dms_runtime_watcher(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "info@ithute.co.ls|{SHA512-CRYPT}$6$old$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))
    before_inode = account_file.stat().st_ino

    mailbox = _mailbox("info@ithute.co.ls", "{SHA512-CRYPT}$6$new$hash")
    assert sync_mailbox(mailbox) is True

    assert account_file.stat().st_ino == before_inode
    assert "info@ithute.co.ls|{SHA512-CRYPT}$6$new$hash" in account_file.read_text(encoding="utf-8")


def test_forwarding_revision_preserves_account_file_inode(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "bda-reg12345@ithute.co.ls|{SHA512-CRYPT}$6$current$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))
    _enable_forwarding_runtime(tmp_path)
    before_inode = account_file.stat().st_ino

    mailbox = _mailbox("bda-reg12345@ithute.co.ls", "{SHA512-CRYPT}$6$current$hash")
    assert sync_mailbox_forwarding(mailbox, "business@gmail.com") is True

    assert account_file.stat().st_ino == before_inode


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


def test_forwarding_fails_closed_until_postfix_runtime_is_verified(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "bda-reg12345@ithute.co.ls|{SHA512-CRYPT}$6$current$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))
    mailbox = _mailbox("bda-reg12345@ithute.co.ls", "{SHA512-CRYPT}$6$current$hash")

    assert sync_mailbox_forwarding(mailbox, "business@gmail.com") is False
    assert not (tmp_path / "postfix-recipient-bcc.cf").exists()


def test_forwarding_keeps_mailbox_account_and_writes_external_copy_rule(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "bda-reg12345@ithute.co.ls|{SHA512-CRYPT}$6$current$hash\n"
        "info@external.example|{SHA512-CRYPT}$6$external$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))
    _enable_forwarding_runtime(tmp_path)

    mailbox = _mailbox("bda-reg12345@ithute.co.ls", "{SHA512-CRYPT}$6$current$hash")
    assert sync_mailbox_forwarding(mailbox, "Business@Gmail.COM") is True

    forwarding_file = tmp_path / "postfix-recipient-bcc.cf"
    assert forwarding_file.read_text(encoding="utf-8") == "bda-reg12345@ithute.co.ls business@gmail.com\n"
    assert forwarding_file.stat().st_mode & 0o777 == 0o600

    accounts = account_file.read_text(encoding="utf-8")
    assert "bda-reg12345@ithute.co.ls|{SHA512-CRYPT}$6$current$hash" in accounts
    assert "info@external.example|{SHA512-CRYPT}$6$external$hash" in accounts
    assert accounts.count("# platform-forwarding-revision:") == 1


def test_forwarding_destination_can_be_replaced_and_disabled(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "bda-reg12345@ithute.co.ls|{SHA512-CRYPT}$6$current$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))
    _enable_forwarding_runtime(tmp_path)
    mailbox = _mailbox("bda-reg12345@ithute.co.ls", "{SHA512-CRYPT}$6$current$hash")

    sync_mailbox_forwarding(mailbox, "first@gmail.com")
    first_marker = [
        line for line in account_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("# platform-forwarding-revision:")
    ][0]

    sync_mailbox_forwarding(mailbox, "second@gmail.com")
    forwarding_file = tmp_path / "postfix-recipient-bcc.cf"
    assert "first@gmail.com" not in forwarding_file.read_text(encoding="utf-8")
    assert forwarding_file.read_text(encoding="utf-8") == "bda-reg12345@ithute.co.ls second@gmail.com\n"
    second_marker = [
        line for line in account_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("# platform-forwarding-revision:")
    ][0]
    assert second_marker != first_marker

    sync_mailbox_forwarding(mailbox, None)
    assert forwarding_file.read_text(encoding="utf-8") == ""
    accounts = account_file.read_text(encoding="utf-8")
    assert "bda-reg12345@ithute.co.ls|{SHA512-CRYPT}$6$current$hash" in accounts
    assert accounts.count("# platform-forwarding-revision:") == 1


def test_forwarding_rejects_self_destination(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "bda-reg12345@ithute.co.ls|{SHA512-CRYPT}$6$current$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))
    _enable_forwarding_runtime(tmp_path)
    mailbox = _mailbox("bda-reg12345@ithute.co.ls", "{SHA512-CRYPT}$6$current$hash")

    try:
        sync_mailbox_forwarding(mailbox, "bda-reg12345@ithute.co.ls")
    except MailAccountSyncError as exc:
        assert "itself" in str(exc)
    else:
        raise AssertionError("self-forwarding was accepted")


def test_suspended_mailbox_removes_forwarding_rule(tmp_path: Path, monkeypatch):
    account_file = tmp_path / "postfix-accounts.cf"
    account_file.write_text(
        "bda-reg12345@ithute.co.ls|{SHA512-CRYPT}$6$current$hash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(account_file))
    _enable_forwarding_runtime(tmp_path)
    mailbox = _mailbox("bda-reg12345@ithute.co.ls", "{SHA512-CRYPT}$6$current$hash")
    sync_mailbox_forwarding(mailbox, "business@gmail.com")

    mailbox.status = MailboxStatus.suspended
    sync_mailbox_forwarding(mailbox, "business@gmail.com")
    assert (tmp_path / "postfix-recipient-bcc.cf").read_text(encoding="utf-8") == ""
