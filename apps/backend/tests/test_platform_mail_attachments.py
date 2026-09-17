from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path

import pytest

from app.schemas.platform_mail_attachments import PlatformMailAttachment, PlatformMailAttachmentSendRequest
from app.services.platform_mail_attachments import attachment_fingerprint, decode_attachments


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "apps" / "backend"
API = BACKEND / "app" / "api" / "v1" / "platform_mail_attachments.py"
ROUTER = BACKEND / "app" / "api" / "v1" / "router.py"
TRANSPORT = BACKEND / "app" / "services" / "platform_mail_attachments.py"


def attachment(content: bytes = b"official attachment") -> PlatformMailAttachment:
    return PlatformMailAttachment(
        filename="notice.pdf",
        content_type="application/pdf",
        content_base64=base64.b64encode(content).decode("ascii"),
    )


def test_attachment_request_contract_is_bounded_and_safe() -> None:
    request = PlatformMailAttachmentSendRequest(
        external_reference="delivery:1",
        recipient="Business@Example.com ",
        subject="Official notice",
        text="Please see attached.",
        attachments=[attachment()],
    )
    assert request.recipient == "business@example.com"
    decoded = decode_attachments(request.attachments)
    assert decoded[0].filename == "notice.pdf"
    assert decoded[0].content == b"official attachment"
    manifest = attachment_fingerprint(decoded)
    assert manifest[0]["size_bytes"] == len(b"official attachment")
    assert len(str(manifest[0]["sha256"])) == 64


def test_attachment_validation_rejects_bad_payloads() -> None:
    with pytest.raises(ValueError, match="filename"):
        PlatformMailAttachment(filename="../notice.pdf", content_type="application/pdf", content_base64="YQ==")

    unsupported = PlatformMailAttachment(filename="notice.exe", content_type="application/x-msdownload", content_base64="YQ==")
    with pytest.raises(ValueError, match="content type"):
        decode_attachments([unsupported])

    invalid = PlatformMailAttachment(filename="notice.pdf", content_type="application/pdf", content_base64="%%%")
    with pytest.raises(ValueError, match="base64"):
        decode_attachments([invalid])


def test_attachment_payload_fingerprint_changes_with_content() -> None:
    first = attachment_fingerprint(decode_attachments([attachment(b"one")]))
    second = attachment_fingerprint(decode_attachments([attachment(b"two")]))
    assert first != second


def test_attachment_endpoint_preserves_platform_mail_security_contract() -> None:
    source = API.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    transport = TRANSPORT.read_text(encoding="utf-8")
    for required in (
        '"/mailboxes/{binding_id}/send-with-attachments"',
        'require_platform_service_scope("mail.send")',
        "_owned_binding",
        "_active_binding_grant",
        "sender=mailbox.address",
        "attachment_fingerprint",
        "payload_hash",
        "attachment_count",
    ):
        assert required in source
    assert "platform_mail_attachments.router" in router
    assert "msg.add_attachment" in transport
    assert "MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024" in transport
    assert "MAX_TOTAL_ATTACHMENT_BYTES = 10 * 1024 * 1024" in transport
    assert "payload.sender" not in source
