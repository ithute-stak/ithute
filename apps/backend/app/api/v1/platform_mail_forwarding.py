from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.platform_service_auth import PlatformServicePrincipal, require_platform_service_scope
from app.api.v1.platform_mail import _active_binding_grant, _audit, _owned_binding
from app.core.config import settings
from app.db.session import get_db
from app.models import MailboxStatus
from app.schemas.platform_mail import PlatformMailboxForwardingRequest, PlatformMailboxForwardingResponse
from app.services.mail_account_sync import MailAccountSyncError, sync_mailbox_forwarding
from app.services.mailboxes import normalize_destination


router = APIRouter(prefix="/platform/mail", tags=["platform-mail"])


def _response(*, binding, mailbox, runtime_synced: bool) -> PlatformMailboxForwardingResponse:
    destination = binding.inbound_forward_to
    return PlatformMailboxForwardingResponse(
        binding_id=binding.id,
        address=mailbox.address,
        destination=destination,
        active=bool(destination and mailbox.status == MailboxStatus.active),
        runtime_synced=runtime_synced,
    )


def _sync_runtime(mailbox, destination: str | None) -> bool:
    try:
        synced = sync_mailbox_forwarding(mailbox, destination)
    except MailAccountSyncError as exc:
        raise HTTPException(status_code=503, detail="Live mail forwarding could not be synchronized") from exc
    if settings.environment.lower() == "production" and not synced:
        raise HTTPException(status_code=503, detail="Live mail forwarding synchronization is not configured")
    return synced


@router.put("/mailboxes/{binding_id}/inbound-forwarding", response_model=PlatformMailboxForwardingResponse)
def configure_inbound_forwarding(
    binding_id: uuid.UUID,
    payload: PlatformMailboxForwardingRequest,
    db: Session = Depends(get_db),
    principal: PlatformServicePrincipal = Depends(require_platform_service_scope("mail.forward")),
) -> PlatformMailboxForwardingResponse:
    binding, mailbox = _owned_binding(db, binding_id=binding_id, principal=principal)
    if mailbox.status != MailboxStatus.active:
        raise HTTPException(status_code=409, detail="Platform mailbox must be active before forwarding can be enabled")
    grant = _active_binding_grant(db, binding=binding, mailbox=mailbox, principal=principal)
    try:
        destination = normalize_destination(payload.destination)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if destination == mailbox.address.lower():
        raise HTTPException(status_code=422, detail="Platform mailbox cannot forward to itself")

    binding.inbound_forward_to = destination
    _audit(
        db,
        action="platform_mail.inbound_forwarding.configured",
        resource_type="platform_mailbox_binding",
        resource_id=str(binding.id),
        tenant_id=mailbox.tenant_id,
        metadata={
            "service_client_id": principal.client_id,
            "token_id": principal.token_id,
            "address": mailbox.address,
            "destination": destination,
            "local_part_prefix": grant.local_part_prefix,
        },
    )
    db.commit()
    db.refresh(binding)

    try:
        runtime_synced = _sync_runtime(mailbox, destination)
    except HTTPException:
        _audit(
            db,
            action="platform_mail.inbound_forwarding.sync_failed",
            resource_type="platform_mailbox_binding",
            resource_id=str(binding.id),
            tenant_id=mailbox.tenant_id,
            metadata={"service_client_id": principal.client_id, "address": mailbox.address},
        )
        db.commit()
        raise
    return _response(binding=binding, mailbox=mailbox, runtime_synced=runtime_synced)


@router.delete("/mailboxes/{binding_id}/inbound-forwarding", response_model=PlatformMailboxForwardingResponse)
def disable_inbound_forwarding(
    binding_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: PlatformServicePrincipal = Depends(require_platform_service_scope("mail.forward")),
) -> PlatformMailboxForwardingResponse:
    binding, mailbox = _owned_binding(db, binding_id=binding_id, principal=principal)
    _active_binding_grant(db, binding=binding, mailbox=mailbox, principal=principal)

    previous = binding.inbound_forward_to
    binding.inbound_forward_to = None
    _audit(
        db,
        action="platform_mail.inbound_forwarding.disabled",
        resource_type="platform_mailbox_binding",
        resource_id=str(binding.id),
        tenant_id=mailbox.tenant_id,
        metadata={
            "service_client_id": principal.client_id,
            "token_id": principal.token_id,
            "address": mailbox.address,
            "previous_destination": previous,
        },
    )
    db.commit()
    db.refresh(binding)

    try:
        runtime_synced = _sync_runtime(mailbox, None)
    except HTTPException:
        _audit(
            db,
            action="platform_mail.inbound_forwarding.sync_failed",
            resource_type="platform_mailbox_binding",
            resource_id=str(binding.id),
            tenant_id=mailbox.tenant_id,
            metadata={"service_client_id": principal.client_id, "address": mailbox.address},
        )
        db.commit()
        raise
    return _response(binding=binding, mailbox=mailbox, runtime_synced=runtime_synced)
