from app.services import external_webmail_read
from app.services.external_webmail import ExternalMailboxConfig, ExternalWebmailError


RAW = b"From: sender@example.com\r\nTo: user@example.com\r\nSubject: Test\r\n\r\nHello from the full message.\r\n"


def config() -> ExternalMailboxConfig:
    return ExternalMailboxConfig(
        address="user@example.com",
        username="user@example.com",
        password="secret",
        display_name="User",
        imap_host="mail.example.com",
        imap_port=993,
        imap_security="ssl",
        smtp_host="mail.example.com",
        smtp_port=465,
        smtp_security="ssl",
    )


class FakeClient:
    def __init__(self, store_status="OK"):
        self.store_status = store_status
        self.calls = []
        self.logged_out = False

    def uid(self, *args):
        self.calls.append(args)
        return self.store_status, []

    def logout(self):
        self.logged_out = True


def test_message_body_opens_even_when_mark_seen_fails(monkeypatch):
    reader = FakeClient()
    writer = FakeClient(store_status="NO")
    clients = [reader, writer]
    selects = []

    monkeypatch.setattr(external_webmail_read, "_imap", lambda _config: clients.pop(0))
    monkeypatch.setattr(
        external_webmail_read,
        "_select",
        lambda client, folder, readonly=False: selects.append((client, folder, readonly)),
    )
    monkeypatch.setattr(
        external_webmail_read,
        "_fetch_raw",
        lambda client, uid, mark_seen=False: (RAW, b"FLAGS ()"),
    )

    result = external_webmail_read.message(config(), "42")

    assert result["body_text"].strip() == "Hello from the full message."
    assert result["seen"] is False
    assert selects[0] == (reader, "INBOX", True)
    assert selects[1] == (writer, "INBOX", False)
    assert writer.calls == [("store", "42", "+FLAGS.SILENT", "(\\Seen)")]
    assert reader.logged_out is True
    assert writer.logged_out is True


def test_message_body_opens_when_provider_rejects_writable_select(monkeypatch):
    reader = FakeClient()
    writer = FakeClient()
    clients = [reader, writer]

    monkeypatch.setattr(external_webmail_read, "_imap", lambda _config: clients.pop(0))

    def select(client, _folder, readonly=False):
        if client is writer and not readonly:
            raise ExternalWebmailError("Unable to open external mailbox folder")

    monkeypatch.setattr(external_webmail_read, "_select", select)
    monkeypatch.setattr(
        external_webmail_read,
        "_fetch_raw",
        lambda client, uid, mark_seen=False: (RAW, b"FLAGS ()"),
    )

    result = external_webmail_read.message(config(), "42")

    assert result["body_text"].strip() == "Hello from the full message."
    assert result["seen"] is False
    assert reader.logged_out is True
    assert writer.logged_out is True


def test_already_seen_message_needs_only_read_connection(monkeypatch):
    reader = FakeClient()
    calls = []

    monkeypatch.setattr(external_webmail_read, "_imap", lambda _config: calls.append(True) or reader)
    monkeypatch.setattr(external_webmail_read, "_select", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        external_webmail_read,
        "_fetch_raw",
        lambda client, uid, mark_seen=False: (RAW, b"FLAGS (\\Seen)"),
    )

    result = external_webmail_read.message(config(), "42")

    assert result["seen"] is True
    assert len(calls) == 1
    assert reader.logged_out is True
