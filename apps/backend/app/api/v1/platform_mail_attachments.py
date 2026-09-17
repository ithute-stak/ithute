from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.platform_service_auth import PlatformServicePrincipal, require_platform_service_scope
from app.api.v1.platform_mail import _active_binding_grant, _audit, _outbound_response, _owned_binding
from app.core.config import settings
from app.db.session import get_db
from app.models import MailboxStatus, PlatformMailOutboundDelivery, TransactionalMessage
from app.schemas.platform_mail import PlatformMailSendResponse
from app.schemas.platform_mail_attachments import PlatformMailAttachmentSendRequest
from app.services.mailboxes import normalize_destination
from app.services.platform_mail_attachments import (
    attachment_fingerprint,
    decode_attachments,
    send_message_with_attachments,
)


router = APIRouter(prefix="/platform/mail", tags=["platform-mail"])


def _payload_hash(
    *,
    binding_id: uuid.UUID,
    recipient: str,
    payload: PlatformMailAttachmentSendRequest,
    attachment_manifest: list[dict[str, str | int]],
) -> str:
    canonical = json.dumps(
        {
            "binding_id": str(binding_id),
            "recipient": recipient,
            "subject": payload.subject,
            "text": payload.text,
            "html": payload.html,
            "attachments": attachment_manifest,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post(
    "/mailboxes/{binding_id}/send-with-attachments",
    response_model=PlatformMailSendResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def send_from_platform_mailbox_with_attachments(
    binding_id: uuid.UUID,
    payload: PlatformMailAttachmentSendRequest,
    db: Session = Depends(get_db),
    principal: PlatformServicePrincipal = Depends(require_platform_service_scope("mail.send")),
) -> PlatformMailSendResponse:
    binding, mailbox = _owned_binding(db, binding_id=binding_id, principal=principal)
    if mailbox.status != MailboxStatus.active:
        raise HTTPException(status_code=409, detail="Platform mailbox is not active")
    _active_binding_grant(db, binding=binding, mailbox=mailbox, principal=principal)

    try:
        recipient = normalize_destination(payload.recipient)
        attachments = decode_attachments(payload.attachments)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    manifest = attachment_fingerprint(attachments)
    payload_hash = _payload_hash(
        binding_id=binding.id,
        recipient=recipient,
        payload=payload,
        attachment_manifest=manifest,
    )
    existing = db.scalar(
        select(PlatformMailOutboundDelivery).where(
            PlatformMailOutboundDelivery.service_client_id == principal.client_id,
            PlatformMailOutboundDelivery.external_reference == payload.external_reference,
        )
    )
    if existing is not None:
        if existing.mailbox_binding_id != binding.id or existing.payload_hash != payload_hash:
            raise HTTPException(status_code=409, detail="Outbound external reference was already used for different content")
        return _outbound_response(existing, binding=binding, mailbox=mailbox)

    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = db.scalar(
        select(func.count(TransactionalMessage.id)).where(
            TransactionalMessage.tenant_id == mailbox.tenant_id,
            TransactionalMessage.created_at >= start,
            TransactionalMessage.status != "failed",
        )
    ) or 0
    if int(sent_today) >= settings.transactional_tenant_daily_limit:
        raise HTTPException(status_code=429, detail="Transactional daily sending limit reached")

    outbound = PlatformMailOutboundDelivery(
        service_client_id=principal.client_id,
        external_reference=payload.external_reference,
        mailbox_binding_id=binding.id,
        recipient=recipient,
        payload_hash=payload_hash,
        status="submitting",
    )
    db.add(outbound)
    try:
        db.commit()
        db.refresh(outbound)
    except IntegrityError:
        db.rollback()
        race = db.scalar(
            select(PlatformMailOutboundDelivery).where(
                PlatformMailOutboundDelivery.service_client_id == principal.client_id,
                PlatformMailOutboundDelivery.external_reference == payload.external_reference,
            )
        )
        if race is None or race.mailbox_binding_id != binding.id or race.payload_hash != payload_hash:
            raise HTTPException(status_code=409, detail="Outbound external reference is already in use")
        return _outbound_response(race, binding=binding, mailbox=mailbox)

    try:
        message = send_message_with_attachments(
            db,
            tenant_id=mailbox.tenant_id,
            sender=mailbox.address,
            recipients=[recipient],
            subject=payload.subject,
            text_body=payload.text,
            html_body=payload.html,
            attachments=attachments,
        )
    except Exception as exc:
        outbound.status = "failed"
        outbound.error = str(exc)[:4000]
        _audit(
            db,
            action="platform_mail.message.failed",
            resource_type="platform_mail_outbound_delivery",
            resource_id=str(outbound.id),
            tenant_id=mailbox.tenant_id,
            metadata={
                "service_client_id": principal.client_id,
                "token_id": principal.token_id,
                "external_reference": outbound.external_reference,
                "sender": mailbox.address,
                "recipient": recipient,
                "attachment_count": len(attachments),
            },
        )
        db.commit()
        return _outbound_response(outbound, binding=binding, mailbox=mailbox)

    outbound.transactional_message_id = message.id
    outbound.provider_message_id = message.message_id
    outbound.status = message.status
    outbound.error = message.error
    _audit(
        db,
        action="platform_mail.message.submitted",
        resource_type="platform_mail_outbound_delivery",
        resource_id=str(outbound.id),
        tenant_id=mailbox.tenant_id,
        metadata={
            "service_client_id": principal.client_id,
            "token_id": principal.token_id,
            "external_reference": outbound.external_reference,
            "sender": mailbox.address,
            "recipient": recipient,
            "provider_message_id": message.message_id,
            "attachment_count": len(attachments),
            "attachment_sha256": [item["sha256"] for item in manifest],
        },
    )
    db.commit()
    db.refresh(outbound)
    return _outbound_response(outbound, binding=binding, mailbox=mailbox)
