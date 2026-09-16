from __future__ import annotations

import json
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.api.platform_service_auth import PlatformServicePrincipal, require_platform_service_scope
from app.db.session import get_db
from app.models import (
    AuditLog,
    Domain,
    DomainStatus,
    Mailbox,
    MailboxStatus,
    PlatformMailDomainGrant,
    PlatformMailboxBinding,
    User,
)
from app.schemas.platform_mail import (
    PlatformMailDomainGrantCreate,
    PlatformMailDomainGrantResponse,
    PlatformMailboxProvisionRequest,
    PlatformMailboxResponse,
    PlatformMailboxStatusResponse,
)
from app.services.mail_account_sync import sync_mailbox
from app.services.mailboxes import hash_mailbox_password, mailbox_address, normalize_local_part


router = APIRouter(prefix="/platform/mail", tags=["platform-mail"])


def _audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    tenant_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, separators=(",", ":"), default=str),
        )
    )


def _domain(db: Session, name: str) -> Domain:
    domain = db.scalar(select(Domain).where(Domain.ascii_name == name.strip().lower().rstrip(".")))
    if domain is None:
        raise HTTPException(status_code=404, detail="Mail domain not found")
    if domain.status != DomainStatus.verified or not domain.mail_enabled:
        raise HTTPException(status_code=409, detail="Mail domain must be verified and mail-enabled")
    return domain


def _grant_for(db: Session, *, client_id: str, domain: Domain) -> PlatformMailDomainGrant:
    grant = db.scalar(
        select(PlatformMailDomainGrant).where(
            PlatformMailDomainGrant.service_client_id == client_id,
            PlatformMailDomainGrant.domain_id == domain.id,
            PlatformMailDomainGrant.active.is_(True),
        )
    )
    if grant is None:
        raise HTTPException(status_code=403, detail="Service client is not allowed to provision this mail domain")
    return grant


def _require_grant_namespace(grant: PlatformMailDomainGrant, local_part: str) -> None:
    if not local_part.startswith(grant.local_part_prefix):
        raise HTTPException(status_code=403, detail="Mailbox local part is outside the service client namespace")


def _grant_response(grant: PlatformMailDomainGrant, domain: Domain) -> PlatformMailDomainGrantResponse:
    return PlatformMailDomainGrantResponse(
        id=grant.id,
        service_client_id=grant.service_client_id,
        domain_id=domain.id,
        domain_name=domain.ascii_name,
        local_part_prefix=grant.local_part_prefix,
        active=grant.active,
        created_at=grant.created_at,
    )


def _binding_response(binding: PlatformMailboxBinding, mailbox: Mailbox) -> PlatformMailboxResponse:
    return PlatformMailboxResponse(
        binding_id=binding.id,
        mailbox_id=mailbox.id,
        service_client_id=binding.service_client_id,
        external_reference=binding.external_reference,
        address=mailbox.address,
        display_name=mailbox.display_name,
        quota_bytes=mailbox.quota_bytes,
        status=mailbox.status.value,
        created_at=binding.created_at,
    )


def _owned_binding(
    db: Session,
    *,
    binding_id: uuid.UUID,
    principal: PlatformServicePrincipal,
) -> tuple[PlatformMailboxBinding, Mailbox]:
    binding = db.get(PlatformMailboxBinding, binding_id)
    if binding is None or binding.service_client_id != principal.client_id:
        raise HTTPException(status_code=404, detail="Platform mailbox not found")
    mailbox = db.get(Mailbox, binding.mailbox_id)
    if mailbox is None:
        raise HTTPException(status_code=410, detail="Platform mailbox no longer exists")
    return binding, mailbox


@router.post("/domain-grants", response_model=PlatformMailDomainGrantResponse, status_code=201)
def create_domain_grant(
    payload: PlatformMailDomainGrantCreate,
    db: Session = Depends(get_db),
    owner: User = Depends(require_platform_owner),
) -> PlatformMailDomainGrantResponse:
    domain = _domain(db, payload.domain_name)
    grant = db.scalar(
        select(PlatformMailDomainGrant).where(
            PlatformMailDomainGrant.service_client_id == payload.service_client_id,
            PlatformMailDomainGrant.domain_id == domain.id,
        )
    )
    if grant is None:
        grant = PlatformMailDomainGrant(
            service_client_id=payload.service_client_id,
            domain_id=domain.id,
            local_part_prefix=payload.local_part_prefix,
            active=True,
            created_by_user_id=owner.id,
        )
        db.add(grant)
        db.flush()
    else:
        grant.local_part_prefix = payload.local_part_prefix
        grant.active = True
        grant.created_by_user_id = owner.id

    _audit(
        db,
        action="platform_mail.domain_grant.upserted",
        resource_type="platform_mail_domain_grant",
        resource_id=str(grant.id),
        tenant_id=domain.tenant_id,
        actor_user_id=owner.id,
        metadata={
            "service_client_id": grant.service_client_id,
            "domain": domain.ascii_name,
            "local_part_prefix": grant.local_part_prefix,
        },
    )
    db.commit()
    db.refresh(grant)
    return _grant_response(grant, domain)


@router.get("/domain-grants", response_model=list[PlatformMailDomainGrantResponse])
def list_domain_grants(
    db: Session = Depends(get_db),
    _owner: User = Depends(require_platform_owner),
) -> list[PlatformMailDomainGrantResponse]:
    rows = db.execute(
        select(PlatformMailDomainGrant, Domain)
        .join(Domain, Domain.id == PlatformMailDomainGrant.domain_id)
        .order_by(PlatformMailDomainGrant.service_client_id, Domain.ascii_name)
    ).all()
    return [_grant_response(grant, domain) for grant, domain in rows]


@router.post("/domain-grants/{grant_id}/disable", response_model=PlatformMailDomainGrantResponse)
def disable_domain_grant(
    grant_id: uuid.UUID,
    db: Session = Depends(get_db),
    owner: User = Depends(require_platform_owner),
) -> PlatformMailDomainGrantResponse:
    grant = db.get(PlatformMailDomainGrant, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Platform mail domain grant not found")
    domain = db.get(Domain, grant.domain_id)
    if domain is None:
        raise HTTPException(status_code=410, detail="Granted domain no longer exists")
    grant.active = False
    _audit(
        db,
        action="platform_mail.domain_grant.disabled",
        resource_type="platform_mail_domain_grant",
        resource_id=str(grant.id),
        tenant_id=domain.tenant_id,
        actor_user_id=owner.id,
        metadata={
            "service_client_id": grant.service_client_id,
            "domain": domain.ascii_name,
            "local_part_prefix": grant.local_part_prefix,
        },
    )
    db.commit()
    db.refresh(grant)
    return _grant_response(grant, domain)


@router.post("/mailboxes", response_model=PlatformMailboxResponse, status_code=201)
def provision_mailbox(
    payload: PlatformMailboxProvisionRequest,
    db: Session = Depends(get_db),
    principal: PlatformServicePrincipal = Depends(require_platform_service_scope("mailbox.create")),
) -> PlatformMailboxResponse:
    domain = _domain(db, payload.domain_name)
    grant = _grant_for(db, client_id=principal.client_id, domain=domain)
    try:
        local_part = normalize_local_part(payload.local_part)
        _require_grant_namespace(grant, local_part)
        address = mailbox_address(local_part, domain.ascii_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    reference = payload.external_reference.strip()
    existing_binding = db.scalar(
        select(PlatformMailboxBinding).where(
            PlatformMailboxBinding.service_client_id == principal.client_id,
            PlatformMailboxBinding.external_reference == reference,
        )
    )
    if existing_binding is not None:
        mailbox = db.get(Mailbox, existing_binding.mailbox_id)
        if mailbox is None:
            raise HTTPException(status_code=409, detail="Existing platform mailbox binding is broken")
        if mailbox.address != address:
            raise HTTPException(status_code=409, detail="External reference is already bound to another mailbox")
        return _binding_response(existing_binding, mailbox)

    address_owner = db.scalar(select(Mailbox).where(Mailbox.address == address))
    if address_owner is not None:
        raise HTTPException(status_code=409, detail="Mailbox address is already in use")

    # Platform-provisioned official addresses are not shared-password accounts.
    # Dovecot still needs a valid credential hash, so generate a high-entropy
    # internal credential, discard the plaintext immediately, and never return it.
    internal_password = secrets.token_urlsafe(48) + "!Aa1"
    mailbox = Mailbox(
        tenant_id=domain.tenant_id,
        domain_id=domain.id,
        local_part=local_part,
        address=address,
        display_name=payload.display_name.strip() if payload.display_name else None,
        password_hash=hash_mailbox_password(internal_password),
        quota_bytes=payload.quota_bytes,
        status=MailboxStatus.active,
        created_by_user_id=grant.created_by_user_id,
    )
    db.add(mailbox)
    db.flush()
    binding = PlatformMailboxBinding(
        service_client_id=principal.client_id,
        external_reference=reference,
        mailbox_id=mailbox.id,
        domain_grant_id=grant.id,
    )
    db.add(binding)
    try:
        db.flush()
        sync_mailbox(mailbox)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Platform mailbox already exists") from exc

    _audit(
        db,
        action="platform_mail.mailbox.provisioned",
        resource_type="mailbox",
        resource_id=str(mailbox.id),
        tenant_id=domain.tenant_id,
        metadata={
            "service_client_id": principal.client_id,
            "token_id": principal.token_id,
            "external_reference": reference,
            "address": mailbox.address,
            "local_part_prefix": grant.local_part_prefix,
            "credential_mode": "platform-managed",
        },
    )
    db.commit()
    db.refresh(binding)
    db.refresh(mailbox)
    return _binding_response(binding, mailbox)


@router.get("/mailboxes/{binding_id}", response_model=PlatformMailboxResponse)
def get_platform_mailbox(
    binding_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: PlatformServicePrincipal = Depends(require_platform_service_scope("mailbox.create")),
) -> PlatformMailboxResponse:
    binding, mailbox = _owned_binding(db, binding_id=binding_id, principal=principal)
    return _binding_response(binding, mailbox)


@router.post("/mailboxes/{binding_id}/suspend", response_model=PlatformMailboxStatusResponse)
def suspend_platform_mailbox(
    binding_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: PlatformServicePrincipal = Depends(require_platform_service_scope("mailbox.create")),
) -> PlatformMailboxStatusResponse:
    binding, mailbox = _owned_binding(db, binding_id=binding_id, principal=principal)
    mailbox.status = MailboxStatus.suspended
    db.flush()
    sync_mailbox(mailbox)
    _audit(
        db,
        action="platform_mail.mailbox.suspended",
        resource_type="mailbox",
        resource_id=str(mailbox.id),
        tenant_id=mailbox.tenant_id,
        metadata={"service_client_id": principal.client_id, "token_id": principal.token_id},
    )
    db.commit()
    return PlatformMailboxStatusResponse(
        binding_id=binding.id, mailbox_id=mailbox.id, address=mailbox.address, status=mailbox.status.value
    )


@router.post("/mailboxes/{binding_id}/reactivate", response_model=PlatformMailboxStatusResponse)
def reactivate_platform_mailbox(
    binding_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: PlatformServicePrincipal = Depends(require_platform_service_scope("mailbox.create")),
) -> PlatformMailboxStatusResponse:
    binding, mailbox = _owned_binding(db, binding_id=binding_id, principal=principal)
    grant = db.get(PlatformMailDomainGrant, binding.domain_grant_id)
    if grant is None or not grant.active:
        raise HTTPException(status_code=403, detail="Mail domain grant is no longer active")
    domain = _domain(db, mailbox.address.split("@", 1)[1])
    if domain.id != mailbox.domain_id or grant.domain_id != domain.id:
        raise HTTPException(status_code=409, detail="Mailbox domain binding is invalid")
    _require_grant_namespace(grant, mailbox.local_part)
    mailbox.status = MailboxStatus.active
    db.flush()
    sync_mailbox(mailbox)
    _audit(
        db,
        action="platform_mail.mailbox.reactivated",
        resource_type="mailbox",
        resource_id=str(mailbox.id),
        tenant_id=mailbox.tenant_id,
        metadata={
            "service_client_id": principal.client_id,
            "token_id": principal.token_id,
            "local_part_prefix": grant.local_part_prefix,
        },
    )
    db.commit()
    return PlatformMailboxStatusResponse(
        binding_id=binding.id, mailbox_id=mailbox.id, address=mailbox.address, status=mailbox.status.value
    )
