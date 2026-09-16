from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner
from app.db.session import get_db
from app.models.domains import Domain, DomainStatus
from app.models.entities import User
from app.models.mail import Mailbox, MailboxStatus, PlatformMailDomainBinding, PlatformMailboxProvisioning
from app.services.ithute_auth import IthuteAuthDisabled, IthuteAuthUnavailable, decode_ithute_service_token
from app.services.mailboxes import hash_mailbox_password, mailbox_address, normalize_local_part

router = APIRouter(prefix="/platform/mail", tags=["platform-mail"])
service_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class MailServiceContext:
    client_id: str
    scopes: frozenset[str]


class DomainBindingCreate(BaseModel):
    service_client_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._:-]*$")
    domain_id: UUID
    allow_create: bool = True
    allow_manage: bool = False


class MailboxProvisionRequest(BaseModel):
    external_reference: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=3, max_length=253)
    local_part: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=150)
    quota_bytes: int = Field(default=1024**3, ge=100 * 1024**2, le=20 * 1024**3)


class MailboxProvisionResponse(BaseModel):
    provisioning_id: UUID
    external_reference: str
    address: str
    status: str
    quota_bytes: int
    domain: str


def _require_service_scope(required_scope: str):
    def dependency(
        credentials: HTTPAuthorizationCredentials = Depends(service_bearer),
    ) -> MailServiceContext:
        if not credentials or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Ithute service token required")
        try:
            claims = decode_ithute_service_token(
                credentials.credentials,
                audience="ithute-mail",
                required_scope=required_scope,
            )
        except IthuteAuthDisabled as exc:
            raise HTTPException(status_code=503, detail="Ithute Auth service verification is disabled") from exc
        except IthuteAuthUnavailable as exc:
            raise HTTPException(status_code=503, detail="Ithute Auth signing keys are temporarily unavailable") from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid or insufficient Ithute service token") from exc
        return MailServiceContext(
            client_id=str(claims["sub"]),
            scopes=frozenset(str(claims.get("scope") or "").split()),
        )
    return dependency


def _domain_for_binding(db: Session, *, client_id: str, domain_name: str, manage: bool = False) -> tuple[Domain, PlatformMailDomainBinding]:
    normalized = domain_name.strip().lower().rstrip(".")
    domain = db.scalar(select(Domain).where(Domain.ascii_name == normalized))
    if domain is None:
        raise HTTPException(status_code=404, detail="Mail domain not found")
    if domain.status != DomainStatus.verified or not domain.mail_enabled:
        raise HTTPException(status_code=409, detail="Mail domain must be verified and mail-enabled")
    binding = db.scalar(
        select(PlatformMailDomainBinding).where(
            PlatformMailDomainBinding.service_client_id == client_id,
            PlatformMailDomainBinding.domain_id == domain.id,
            PlatformMailDomainBinding.active.is_(True),
        )
    )
    if binding is None or (manage and not binding.allow_manage) or (not manage and not binding.allow_create):
        raise HTTPException(status_code=403, detail="Service client is not authorized for this mail domain")
    return domain, binding


def _owned_provisioning(db: Session, *, client_id: str, external_reference: str) -> tuple[PlatformMailboxProvisioning, Mailbox, Domain]:
    provisioning = db.scalar(
        select(PlatformMailboxProvisioning).where(
            PlatformMailboxProvisioning.service_client_id == client_id,
            PlatformMailboxProvisioning.external_reference == external_reference,
        )
    )
    if provisioning is None:
        raise HTTPException(status_code=404, detail="Provisioned mailbox not found")
    mailbox = db.get(Mailbox, provisioning.mailbox_id)
    domain = db.get(Domain, provisioning.domain_id)
    if mailbox is None or domain is None:
        raise HTTPException(status_code=409, detail="Provisioned mailbox record is incomplete")
    return provisioning, mailbox, domain


def _response(provisioning: PlatformMailboxProvisioning, mailbox: Mailbox, domain: Domain) -> MailboxProvisionResponse:
    return MailboxProvisionResponse(
        provisioning_id=provisioning.id,
        external_reference=provisioning.external_reference,
        address=mailbox.address,
        status=mailbox.status.value,
        quota_bytes=mailbox.quota_bytes,
        domain=domain.ascii_name,
    )


@router.post("/domain-bindings", status_code=201)
def bind_service_client_to_domain(
    payload: DomainBindingCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    domain = db.get(Domain, payload.domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    if domain.status != DomainStatus.verified or not domain.mail_enabled:
        raise HTTPException(status_code=409, detail="Domain must be verified and mail-enabled before binding")
    binding = db.scalar(
        select(PlatformMailDomainBinding).where(
            PlatformMailDomainBinding.service_client_id == payload.service_client_id,
            PlatformMailDomainBinding.domain_id == payload.domain_id,
        )
    )
    if binding is None:
        binding = PlatformMailDomainBinding(
            service_client_id=payload.service_client_id,
            domain_id=payload.domain_id,
            allow_create=payload.allow_create,
            allow_manage=payload.allow_manage,
            active=True,
            created_by_user_id=current.id,
        )
        db.add(binding)
    else:
        binding.allow_create = payload.allow_create
        binding.allow_manage = payload.allow_manage
        binding.active = True
    db.commit()
    db.refresh(binding)
    return {
        "id": str(binding.id),
        "service_client_id": binding.service_client_id,
        "domain_id": str(binding.domain_id),
        "domain": domain.ascii_name,
        "allow_create": binding.allow_create,
        "allow_manage": binding.allow_manage,
        "active": binding.active,
    }


@router.post("/mailboxes", response_model=MailboxProvisionResponse, status_code=201)
def provision_mailbox(
    payload: MailboxProvisionRequest,
    db: Session = Depends(get_db),
    context: MailServiceContext = Depends(_require_service_scope("mailbox.create")),
):
    reference = payload.external_reference.strip()
    existing = db.scalar(
        select(PlatformMailboxProvisioning).where(
            PlatformMailboxProvisioning.service_client_id == context.client_id,
            PlatformMailboxProvisioning.external_reference == reference,
        )
    )
    if existing is not None:
        mailbox = db.get(Mailbox, existing.mailbox_id)
        domain = db.get(Domain, existing.domain_id)
        if mailbox is None or domain is None:
            raise HTTPException(status_code=409, detail="Existing provisioning record is incomplete")
        requested_address = mailbox_address(normalize_local_part(payload.local_part), payload.domain)
        if mailbox.address != requested_address:
            raise HTTPException(status_code=409, detail="External reference is already bound to another mailbox")
        return _response(existing, mailbox, domain)

    domain, _ = _domain_for_binding(db, client_id=context.client_id, domain_name=payload.domain)
    try:
        local_part = normalize_local_part(payload.local_part)
        address = mailbox_address(local_part, domain.ascii_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if db.scalar(select(Mailbox).where(Mailbox.address == address)) is not None:
        raise HTTPException(status_code=409, detail="Mailbox address is already in use")

    # The machine caller never chooses or receives the mailbox credential.
    # It is an infrastructure credential; the business owner authenticates to
    # the future official-inbox product through central Ithute Auth.
    generated_secret = f"{secrets.token_urlsafe(36)}!A9"
    mailbox = Mailbox(
        tenant_id=domain.tenant_id,
        domain_id=domain.id,
        local_part=local_part,
        address=address,
        display_name=payload.display_name,
        password_hash=hash_mailbox_password(generated_secret),
        quota_bytes=payload.quota_bytes,
        status=MailboxStatus.active,
        created_by_user_id=None,
        created_by_service_client_id=context.client_id,
    )
    db.add(mailbox)
    db.flush()
    provisioning = PlatformMailboxProvisioning(
        service_client_id=context.client_id,
        external_reference=reference,
        mailbox_id=mailbox.id,
        domain_id=domain.id,
    )
    db.add(provisioning)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mailbox provisioning conflicts with an existing record") from exc
    db.refresh(mailbox)
    db.refresh(provisioning)
    return _response(provisioning, mailbox, domain)


@router.get("/mailboxes/{external_reference:path}", response_model=MailboxProvisionResponse)
def get_provisioned_mailbox(
    external_reference: str,
    db: Session = Depends(get_db),
    context: MailServiceContext = Depends(_require_service_scope("mailbox.create")),
):
    provisioning, mailbox, domain = _owned_provisioning(
        db, client_id=context.client_id, external_reference=external_reference
    )
    return _response(provisioning, mailbox, domain)


@router.post("/mailboxes/{external_reference:path}/suspend", response_model=MailboxProvisionResponse)
def suspend_provisioned_mailbox(
    external_reference: str,
    db: Session = Depends(get_db),
    context: MailServiceContext = Depends(_require_service_scope("mailbox.manage")),
):
    provisioning, mailbox, domain = _owned_provisioning(db, client_id=context.client_id, external_reference=external_reference)
    _domain_for_binding(db, client_id=context.client_id, domain_name=domain.ascii_name, manage=True)
    if mailbox.status == MailboxStatus.archived:
        raise HTTPException(status_code=409, detail="Archived mailbox cannot be suspended")
    mailbox.status = MailboxStatus.suspended
    db.commit()
    db.refresh(mailbox)
    return _response(provisioning, mailbox, domain)


@router.post("/mailboxes/{external_reference:path}/activate", response_model=MailboxProvisionResponse)
def activate_provisioned_mailbox(
    external_reference: str,
    db: Session = Depends(get_db),
    context: MailServiceContext = Depends(_require_service_scope("mailbox.manage")),
):
    provisioning, mailbox, domain = _owned_provisioning(db, client_id=context.client_id, external_reference=external_reference)
    _domain_for_binding(db, client_id=context.client_id, domain_name=domain.ascii_name, manage=True)
    if mailbox.status == MailboxStatus.archived:
        raise HTTPException(status_code=409, detail="Archived mailbox cannot be activated")
    mailbox.status = MailboxStatus.active
    db.commit()
    db.refresh(mailbox)
    return _response(provisioning, mailbox, domain)
