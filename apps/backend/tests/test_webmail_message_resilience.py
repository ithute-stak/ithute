from types import SimpleNamespace

import pytest

from app.services import webmail
from app.services.engine_runtime import MimeScan


class FakeMailbox:
    def __init__(self):
        self.selected = None
        self.logout_calls = 0

    def select(self, folder, readonly=False):
        self.selected = (folder, readonly)
        return "OK", [b"2"]

    def uid(self, command, *args):
        if command == "search":
            return "OK", [b"1 2"]
        raise AssertionError(f"unexpected IMAP command: {command}")

    def logout(self):
        self.logout_calls += 1
        return "BYE", []


def test_binary_single_part_message_is_rendered_as_text():
    raw = (
        b"From: sender@example.com\r\n"
        b"To: person@example.com\r\n"
        b"Subject: Binary body\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"\r\n"
        b"\xff\x00binary payload"
    )

    row = webmail._message_json("42", raw, b"42 (FLAGS (\\Seen))", include_body=True)

    assert row["uid"] == "42"
    assert row["subject"] == "Binary body"
    assert isinstance(row["body_text"], str)
    assert "binary payload" in row["body_text"]
    assert "binary payload" in row["snippet"]


def test_messages_skips_one_unreadable_message_without_breaking_inbox(monkeypatch):
    client = FakeMailbox()
    monkeypatch.setattr(webmail, "_imap", lambda *_: client)

    def fake_fetch(_client, uid, mark_seen=False):
        assert mark_seen is False
        return f"Subject: message {uid}\r\n\r\nbody".encode(), b""

    real_message_json = webmail._message_json

    def fake_message_json(uid, raw, meta=b"", include_body=False):
        if uid == "2":
            raise ValueError("malformed MIME")
        return real_message_json(uid, raw, meta, include_body)

    monkeypatch.setattr(webmail, "_fetch_raw", fake_fetch)
    monkeypatch.setattr(webmail, "_message_json", fake_message_json)

    result = webmail.messages("person@example.com", "secret")

    assert result["total"] == 2
    assert result["skipped"] == 1
    assert [item["uid"] for item in result["items"]] == ["1"]
    assert client.logout_calls == 1


def test_message_converts_parser_failure_to_webmail_error(monkeypatch):
    client = FakeMailbox()
    monkeypatch.setattr(webmail, "_imap", lambda *_: client)
    monkeypatch.setattr(webmail, "_fetch_raw", lambda *_args, **_kwargs: (b"broken", b""))
    monkeypatch.setattr(webmail, "_message_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("broken MIME")))

    with pytest.raises(webmail.WebmailError, match="Unable to read message"):
        webmail.message("person@example.com", "secret", "9")

    assert client.logout_calls == 1



class WalkMustNotRun:
    def walk(self):
        raise AssertionError("MIME tree walk should have been skipped")


def test_attachment_walk_is_skipped_when_prescan_proves_no_attachment_signal():
    scan = MimeScan(
        bytes=100,
        header_bytes=50,
        body_bytes=50,
        lines=5,
        crlf_lines=4,
        non_ascii=0,
        nul_bytes=0,
        boundary_markers=0,
        attachment_signals=0,
    )

    assert webmail._attachments(WalkMustNotRun(), scan) == []


def test_message_json_uses_prescan_but_keeps_python_parser_authoritative(monkeypatch):
    raw = (
        b"From: sender@example.com\r\n"
        b"To: person@example.com\r\n"
        b"Subject: Native pre-scan\r\n"
        b"\r\n"
        b"hello"
    )
    scan = MimeScan(
        bytes=len(raw),
        header_bytes=84,
        body_bytes=5,
        lines=5,
        crlf_lines=4,
        non_ascii=0,
        nul_bytes=0,
        boundary_markers=0,
        attachment_signals=0,
    )
    monkeypatch.setattr(
        webmail,
        "execute_binary",
        lambda operation, value: SimpleNamespace(value=scan, engine="rust"),
    )

    row = webmail._message_json("77", raw, b"")

    assert row["uid"] == "77"
    assert row["subject"] == "Native pre-scan"
    assert row["snippet"] == "hello"
    assert row["attachments"] == []


def test_attachment_metadata_includes_engine_routed_sha256(monkeypatch):
    raw = (
        b"From: sender@example.com\r\n"
        b"To: person@example.com\r\n"
        b"Subject: Attachment digest\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=x\r\n"
        b"\r\n"
        b"--x\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\nhello\r\n"
        b"--x\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment; filename=\"proof.bin\"\r\n"
        b"Content-Transfer-Encoding: base64\r\n\r\n"
        b"aXRodXRl\r\n"
        b"--x--\r\n"
    )
    scan = MimeScan(
        bytes=len(raw),
        header_bytes=150,
        body_bytes=max(0, len(raw) - 150),
        lines=16,
        crlf_lines=15,
        non_ascii=0,
        nul_bytes=0,
        boundary_markers=3,
        attachment_signals=1,
    )

    def fake_execute(operation, value):
        if operation == "mail.mime_scan":
            return SimpleNamespace(value=scan, engine="rust")
        if operation == "mail.sha256":
            assert value == b"ithute"
            return SimpleNamespace(value="digest-from-rust", engine="rust")
        if operation == "native.blob_profile":
            assert value == b"ithute"
            return SimpleNamespace(
                value=SimpleNamespace(
                    fnv1a64=123456,
                    nul_bytes=0,
                    control_bytes=0,
                    high_bytes=0,
                ),
                engine="cpp",
            )
        raise AssertionError(operation)

    monkeypatch.setattr(webmail, "execute_binary", fake_execute)

    row = webmail._message_json("88", raw, b"")

    assert row["attachments"] == [
        {
            "index": 0,
            "filename": "proof.bin",
            "content_type": "application/octet-stream",
            "size": 6,
            "sha256": "digest-from-rust",
            "fingerprint": "123456",
            "nul_bytes": 0,
            "control_bytes": 0,
            "high_bytes": 0,
            "profile_engine": "cpp",
        }
    ]



def test_structured_html_message_gets_safe_universal_render_contract(monkeypatch):
    raw = (
        b"From: sender@example.com\r\n"
        b"To: person@example.com\r\n"
        b"Subject: Receipt\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/alternative; boundary=x\r\n"
        b"\r\n"
        b"--x\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nPaid M100.00\r\n"
        b"--x\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        b"<style>body{position:fixed}</style><script>alert(1)</script>"
        b"<h1>Receipt</h1><table><tr><td>Paid M100.00</td></tr></table>"
        b"<img src='https://tracker.example/pixel.png'>\r\n--x--\r\n"
    )

    real_execute = webmail.execute_binary

    def fake_execute(operation, value):
        if operation == "mail.mime_scan":
            return real_execute(operation, value)
        if operation == "native.blob_profile":
            return SimpleNamespace(
                value=SimpleNamespace(
                    fnv1a64=1,
                    nul_bytes=0,
                    control_bytes=0,
                    high_bytes=0,
                ),
                engine="cpp",
            )
        return real_execute(operation, value)

    monkeypatch.setattr(webmail, "execute_binary", fake_execute)
    monkeypatch.setattr(
        webmail,
        "execute_mail_render_plan",
        lambda metrics: SimpleNamespace(
            engine="go",
            value={
                "engine": "go",
                "layout": "transactional",
                "reader_width": "wide",
                "horizontal_fit": "scroll_tables",
                "density": "compact",
                "collapse_quotes": False,
            },
        ),
    )
    monkeypatch.setattr(
        webmail,
        "execute_mail_structured_profile",
        lambda metrics: SimpleNamespace(
            engine="java",
            value={
                "engine": "java",
                "semantic_type": "transactional",
                "collapse_quoted_history": False,
                "preserve_semantic_tables": True,
                "prefer_readable_width": False,
                "standards_profile": "email-content-v1",
            },
        ),
    )

    row = webmail._message_json("99", raw, b"", include_body=True)

    assert "<script" not in row["body_html"].lower()
    assert "<style" not in row["body_html"].lower()
    assert "<img" not in row["body_html"].lower()
    assert "<table" in row["body_html"].lower()
    assert row["render_contract"]["kind"] == "transactional_table"
    assert row["render_contract"]["engines"]["layout_plan"] == "go"
    assert row["render_contract"]["engines"]["structured_profile"] == "java"
    assert row["render_contract"]["engines"]["text_shape"] == "cpp"


def test_plain_message_render_contract_falls_back_without_html(monkeypatch):
    raw = (
        b"From: sender@example.com\r\n"
        b"To: person@example.com\r\n"
        b"Subject: Plain\r\n"
        b"\r\n"
        b"Hello there"
    )
    monkeypatch.setattr(
        webmail,
        "execute_mail_render_plan",
        lambda metrics: SimpleNamespace(engine="python-fallback", value={"layout": "document", "density": "compact"}),
    )
    monkeypatch.setattr(
        webmail,
        "execute_mail_structured_profile",
        lambda metrics: SimpleNamespace(engine="python-fallback", value={"semantic_type": "message"}),
    )

    row = webmail._message_json("100", raw, b"", include_body=True)

    assert row["body_html"] == ""
    assert row["render_contract"]["kind"] == "plain"
    assert row["render_contract"]["has_plain"] is True



def test_conversation_segments_collapse_reply_history():
    segments = webmail._conversation_segments(
        "Thanks, that works.\n\nOn Tue, Alice wrote:\n> Previous message\n> More history",
        "",
    )

    assert segments["main_text"] == "Thanks, that works."
    assert "Previous message" in segments["quoted_text"]
    assert segments["has_quoted_history"] is True


def test_conversation_segments_separate_mobile_signature():
    segments = webmail._conversation_segments(
        "Approved.\n\nSent from my iPhone",
        "",
    )

    assert segments["main_text"] == "Approved."
    assert segments["signature_text"] == "Sent from my iPhone"
    assert segments["has_signature"] is True


def test_conversation_segments_deemphasize_footer():
    segments = webmail._conversation_segments(
        "Your monthly statement is ready.\n\nManage preferences or unsubscribe from these notices.",
        "",
    )

    assert segments["main_text"] == "Your monthly statement is ready."
    assert "unsubscribe" in segments["footer_text"].lower()
    assert segments["has_footer"] is True


def test_conversation_segments_split_safe_html_blockquote():
    segments = webmail._conversation_segments(
        "Current reply\nPrevious reply",
        "<p>Current reply</p><blockquote><p>Previous reply</p></blockquote>",
    )

    assert segments["main_html"] == "<p>Current reply</p>"
    assert segments["quoted_html"].startswith("<blockquote>")
    assert segments["has_quoted_history"] is True


def test_render_contract_contains_conversation_metadata(monkeypatch):
    raw = (
        b"From: sender@example.com\r\n"
        b"To: person@example.com\r\n"
        b"Subject: Re: Update\r\n"
        b"\r\n"
        b"Looks good.\n\nOn Tue, Alice wrote:\n> Earlier content"
    )
    monkeypatch.setattr(
        webmail,
        "execute_mail_render_plan",
        lambda metrics: SimpleNamespace(engine="python-fallback", value={"layout": "document", "density": "compact"}),
    )
    monkeypatch.setattr(
        webmail,
        "execute_mail_structured_profile",
        lambda metrics: SimpleNamespace(engine="python-fallback", value={"semantic_type": "conversation_heavy", "collapse_quoted_history": True}),
    )

    row = webmail._message_json("101", raw, b"", include_body=True)

    conversation = row["render_contract"]["conversation"]
    assert conversation["main_text"] == "Looks good."
    assert conversation["has_quoted_history"] is True
    assert conversation["collapse_quoted_history"] is True



def test_thread_metadata_normalizes_reply_and_forward_prefixes():
    raw = (
        b"Message-ID: <child@example.com>\r\n"
        b"In-Reply-To: <parent@example.com>\r\n"
        b"References: <root@example.com> <parent@example.com>\r\n"
        b"From: Alice <alice@example.com>\r\n"
        b"To: Bob <bob@example.com>\r\n"
        b"Subject: Re: Fwd: [External] Quarterly Update\r\n"
        b"\r\n"
        b"Latest reply"
    )

    row = webmail._message_json("200", raw, b"", include_body=False)

    assert row["thread"]["message_id_tokens"] == ["<child@example.com>"]
    assert row["thread"]["in_reply_to_tokens"] == ["<parent@example.com>"]
    assert row["thread"]["reference_tokens"] == ["<root@example.com>", "<parent@example.com>"]
    assert row["thread"]["subject_key"] == "quarterly update"


def test_thread_metadata_handles_missing_message_ids_safely():
    raw = (
        b"From: Alice <alice@example.com>\r\n"
        b"To: Bob <bob@example.com>\r\n"
        b"Subject: Re: Status\r\n"
        b"\r\n"
        b"Hello"
    )

    row = webmail._message_json("201", raw, b"", include_body=False)

    assert row["thread"]["message_id_tokens"] == []
    assert row["thread"]["in_reply_to_tokens"] == []
    assert row["thread"]["reference_tokens"] == []
    assert row["thread"]["subject_key"] == "status"
