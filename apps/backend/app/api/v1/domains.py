import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AuditLog,
    ConnectedMailAccount,
    EdgeApplication,
    GroupwareCredential,
    MailMigrationJob,
    MailboxDelegate,
    MailboxPolicy,
    MailboxRecoveryJob,
    Tenant,
    TenantStatus,
    User,
)
from app.models.deliverability import DkimKey
from app.models.domains import Domain, DomainDnsMode, DomainEvent, DomainStatus, DomainVerificationAttempt, DomainVerificationMethod
from app.models.mail import DistributionGroup, MailAlias, Mailbox
from app.schemas.domains import (
    DomainChallengeResponse,
    DomainCreate,
    DomainCreateResponse,
    DomainEventRead,
    DomainListResponse,
    DomainRead,
    DomainReadiness,
    DomainStatusUpdate,
    DomainTransferRequest,
    DomainUpdate,
    DomainVerificationAttemptRead,
    DomainVerifyRequest,
    DomainVerifyResponse,
)
from app.services.billing import require_entitlement
from app.services.domain_discovery import platform_nameservers_ready
from app.services.domains import (
    add_domain_event,
    new_verification_token,
    normalize_domain,
    record_name,
    token_hash,
    verification_value,
    verify_domain,
)

router = APIRouter(prefix="/tenants/{tenant_id}/domains", tags=["domains"])


def _domain_or_404(db: Session, tenant_id: UUID, domain_id: UUID) -> Domain:
    domain = db.scalar(select(Domain).where(Domain.id == domain_id, Domain.tenant_id == tenant_id))
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    return domain


def _audit(db: Session, tenant_id: UUID, actor: User, action: str, domain: Domain, metadata: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        action=action,
        resource_type="domain",
        resource_id=str(domain.id),
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


def _move_domain_operational_resources(db: Session, domain: Domain, source_tenant_id: UUID, target_tenant_id: UUID) -> None:
    """Move current domain-owned configuration without rewriting historical audit data.

    Domain and mailbox resources carry tenant IDs of their own, so changing only
    domains.tenant_id would leave an internally inconsistent cross-tenant graph.
    Historical domain events, verification attempts, analytics and audit rows
    intentionally retain the organization that owned the domain when they were made.
    """
    mailbox_ids = select(Mailbox.id).where(Mailbox.domain_id == domain.id)

    for model in (Mailbox, MailAlias, DistributionGroup, DkimKey, EdgeApplication):
        db.execute(
            update(model)
            .where(model.tenant_id == source_tenant_id, model.domain_id == domain.id)
            .values(tenant_id=target_tenant_id)
        )

    for model in (
        ConnectedMailAccount,
        GroupwareCredential,
        MailMigrationJob,
        MailboxDelegate,
        MailboxPolicy,
        MailboxRecoveryJob,
    ):
        db.execute(
            update(model)
            .where(model.tenant_id == source_tenant_id, model.mailbox_id.in_(mailbox_ids))
            .values(tenant_id=target_tenant_id)
        )


def _enforce_verification_throttle(db: Session, domain: Domain) -> None:
    now = datetime.now(timezone.utc)
    latest = db.scalar(
        select(DomainVerificationAttempt)
        .where(DomainVerificationAttempt.domain_id == domain.id)
        .order_by(DomainVerificationAttempt.created_at.desc())
        .limit(1)
    )
    if latest and latest.created_at:
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < settings.domain_verification_min_interval_seconds:
            retry_after = max(1, int(settings.domain_verification_min_interval_seconds - elapsed))
            raise HTTPException(status_code=429, detail=f"Verification throttled; retry in {retry_after} seconds")
    since = now - timedelta(hours=1)
    attempts = db.scalar(
        select(func.count()).select_from(DomainVerificationAttempt).where(
            DomainVerificationAttempt.domain_id == domain.id,
            DomainVerificationAttempt.created_at >= since,
        )
    ) or 0
    if attempts >= settings.domain_verification_max_attempts_per_hour:
        raise HTTPException(status_code=429, detail="Hourly domain verification attempt limit reached")


def _release_blockers(db: Session, domain: Domain) -> list[str]:
    """Return operational resources that make a hard domain release unsafe.

    Permanent release is intentionally conservative: clean, unverified claims may
    be removed immediately, but domains that entered a live DNS/mail lifecycle
    must be deprovisioned explicitly first. This prevents a database deletion
    from leaving PowerDNS, Rspamd or live mail routing behind.
    """
    blockers: list[str] = []

    if domain.ownership_verified_at is not None:
        blockers.append("verified ownership lifecycle")

    provisioned_dns = db.scalar(
        select(DomainEvent.id)
        .where(
            DomainEvent.domain_id == domain.id,
            DomainEvent.event_type.in_(("dns.zone_provisioned", "dns.zone_reconciled")),
        )
        .limit(1)
    )
    if provisioned_dns is not None:
        blockers.append("authoritative DNS zone")

    resources = (
        ("mailboxes", Mailbox),
        ("mail aliases", MailAlias),
        ("distribution groups", DistributionGroup),
        ("DKIM signing keys", DkimKey),
    )
    for label, model in resources:
        exists = db.scalar(select(model.id).where(model.domain_id == domain.id).limit(1))
        if exists is not None:
            blockers.append(label)

    return blockers


def _verification_method_for_new_domain(ascii_name: str, dns_mode: DomainDnsMode) -> DomainVerificationMethod:
    if dns_mode == DomainDnsMode.external:
        return DomainVerificationMethod.txt

    # Managed authoritative DNS follows the Cloudflare-style full-zone model:
    # stage the zone first, then prove control by changing the registrar/registry
    # delegation to BOTH Ithute nameservers. Existing DNS records change the
    # migration plan, not the ownership mechanism, so no TXT challenge is needed.
    platform_nameservers = [settings.nameserver_1, settings.nameserver_2]
    if not platform_nameservers_ready(platform_nameservers):
        raise HTTPException(
            status_code=503,
            detail=(
                "Managed DNS onboarding is unavailable because the public Ithute nameservers are not configured. "
                "No TXT fallback is used for managed DNS."
            ),
        )
    return DomainVerificationMethod.nameserver


@router.post("", response_model=DomainCreateResponse, status_code=status.HTTP_201_CREATED)
def create_domain(tenant_id: UUID, payload: DomainCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    try:
        require_entitlement(db, tenant_id, "domain")
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=f"Billing entitlement denied: {exc}") from exc
    try:
        ascii_name, unicode_name = normalize_domain(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = db.scalar(select(Domain).where(Domain.ascii_name == ascii_name))
    if existing:
        if existing.tenant_id == tenant_id:
            raise HTTPException(status_code=409, detail="Domain already exists in this organization")
        raise HTTPException(status_code=409, detail="Domain is already claimed by another organization")

    # Recompute the ownership policy on the server at creation time. Browser
    # inspection is advisory only. Managed PowerDNS always uses NS delegation;
    # External DNS keeps TXT because Ithute will not become authoritative there.
    verification_method = _verification_method_for_new_domain(ascii_name, payload.dns_mode)

    token = new_verification_token()
    domain = Domain(
        tenant_id=tenant_id,
        ascii_name=ascii_name,
        unicode_name=unicode_name,
        dns_mode=payload.dns_mode,
        mail_enabled=payload.mail_enabled,
        notes=payload.notes,
        verification_method=verification_method.value,
        verification_token_hash=token_hash(token),
        verification_token_hint=token[-8:] if verification_method == DomainVerificationMethod.txt else "not-needed",
        verification_record_name=record_name(ascii_name),
        created_by_user_id=current.id,
    )
    db.add(domain)
    db.flush()
    add_domain_event(db, domain, current.id, "domain.created", {"ascii_name": ascii_name, "verification_method": verification_method.value})
    _audit(db, tenant_id, current, "domain.create", domain, {"ascii_name": ascii_name, "verification_method": verification_method.value})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Domain already exists") from exc
    db.refresh(domain)
    data = DomainRead.model_validate(domain).model_dump()
    disclosed_value = verification_value(token) if verification_method == DomainVerificationMethod.txt else None
    return DomainCreateResponse(**data, verification_value=disclosed_value)


@router.get("", response_model=DomainListResponse)
def list_domains(
    tenant_id: UUID,
    q: str | None = Query(default=None, max_length=253),
    domain_status: DomainStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    filters = [Domain.tenant_id == tenant_id]
    if domain_status:
        filters.append(Domain.status == domain_status)
    if q:
        filters.append(Domain.ascii_name.ilike(f"%{q.strip().lower()}%"))
    total = db.scalar(select(func.count()).select_from(Domain).where(*filters)) or 0
    items = db.scalars(select(Domain).where(*filters).order_by(Domain.ascii_name.asc()).offset(offset).limit(limit)).all()
    return DomainListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{domain_id}", response_model=DomainRead)
def get_domain(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    return _domain_or_404(db, tenant_id, domain_id)


@router.patch("/{domain_id}", response_model=DomainRead)
def update_domain(tenant_id: UUID, domain_id: UUID, payload: DomainUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    if domain.status == DomainStatus.archived:
        raise HTTPException(status_code=409, detail="Archived domains are read-only")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(domain, field, value)
    if domain.ownership_verified_at is None:
        if domain.dns_mode == DomainDnsMode.external:
            domain.verification_method = DomainVerificationMethod.txt.value
        elif domain.dns_mode == DomainDnsMode.platform:
            if not platform_nameservers_ready([settings.nameserver_1, settings.nameserver_2]):
                raise HTTPException(status_code=503, detail="Managed DNS onboarding is unavailable because the public Ithute nameservers are not configured")
            domain.verification_method = DomainVerificationMethod.nameserver.value
            domain.verification_token_hint = "not-needed"
    add_domain_event(db, domain, current.id, "domain.updated", changes)
    _audit(db, tenant_id, current, "domain.update", domain, changes)
    db.commit()
    db.refresh(domain)
    return domain


@router.post("/{domain_id}/transfer", response_model=DomainRead)
def transfer_domain(
    tenant_id: UUID,
    domain_id: UUID,
    payload: DomainTransferRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # Changing ownership is an organization-administration action, not a normal
    # DNS edit. Require tenant-admin authority on both sides; platform owners
    # retain the normal permission bypass in require_tenant_permission().
    require_tenant_permission(tenant_id, "identity.manage", db, current)
    domain = db.scalar(
        select(Domain)
        .where(Domain.id == domain_id, Domain.tenant_id == tenant_id)
        .with_for_update()
    )
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    if payload.target_tenant_id == tenant_id:
        raise HTTPException(status_code=409, detail="Domain already belongs to this organization")
    if domain.status == DomainStatus.archived:
        raise HTTPException(status_code=409, detail="Archived domains cannot be transferred")

    target = db.get(Tenant, payload.target_tenant_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target organization not found")
    if target.status != TenantStatus.active:
        raise HTTPException(status_code=409, detail="Target organization must be active")
    require_tenant_permission(payload.target_tenant_id, "identity.manage", db, current)

    try:
        require_entitlement(db, payload.target_tenant_id, "domain")
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=f"Target organization billing entitlement denied: {exc}") from exc

    source_tenant_id = domain.tenant_id
    metadata = {
        "ascii_name": domain.ascii_name,
        "from_tenant_id": str(source_tenant_id),
        "to_tenant_id": str(payload.target_tenant_id),
    }

    # Capture the transfer-out side while the domain still belongs to source.
    add_domain_event(db, domain, current.id, "domain.transfer_out", metadata)
    _audit(db, source_tenant_id, current, "domain.transfer_out", domain, metadata)

    _move_domain_operational_resources(db, domain, source_tenant_id, payload.target_tenant_id)
    domain.tenant_id = payload.target_tenant_id
    db.flush()

    # Capture a corresponding destination event. The same domain id, DNS state,
    # verification state and operational resources are preserved; only ownership moves.
    add_domain_event(db, domain, current.id, "domain.transfer_in", metadata)
    _audit(db, payload.target_tenant_id, current, "domain.transfer_in", domain, metadata)
    db.commit()
    db.refresh(domain)
    return domain


@router.post("/{domain_id}/challenge", response_model=DomainChallengeResponse)
def regenerate_challenge(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    if domain.status == DomainStatus.archived:
        raise HTTPException(status_code=409, detail="Archived domain cannot be re-verified")
    if domain.verification_method != DomainVerificationMethod.txt.value:
        raise HTTPException(status_code=409, detail="TXT verification is not required for this domain; verify ownership by nameserver delegation")
    token = new_verification_token()
    domain.verification_token_hash = token_hash(token)
    domain.verification_token_hint = token[-8:]
    domain.status = DomainStatus.pending_verification
    domain.ownership_verified_at = None
    add_domain_event(db, domain, current.id, "domain.challenge_regenerated")
    _audit(db, tenant_id, current, "domain.challenge_regenerate", domain)
    db.commit()
    return DomainChallengeResponse(domain_id=domain.id, record_name=domain.verification_record_name, verification_value=verification_value(token))


@router.post("/{domain_id}/verify", response_model=DomainVerifyResponse)
def verify_domain_ownership(
    tenant_id: UUID,
    domain_id: UUID,
    payload: DomainVerifyRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    if domain.status == DomainStatus.archived:
        raise HTTPException(status_code=409, detail="Archived domain cannot be verified")
    _enforce_verification_throttle(db, domain)
    success, observed, error = verify_domain(domain, payload.token, current.id, db)
    event = "domain.ownership_verified" if success else "domain.verification_failed"
    add_domain_event(db, domain, current.id, event, {"error": error, "observed_count": len(observed), "verification_method": domain.verification_method})
    _audit(db, tenant_id, current, "domain.verify", domain, {"success": success, "error": error, "verification_method": domain.verification_method})
    db.commit()
    db.refresh(domain)
    return DomainVerifyResponse(verified=success, status=domain.status, observed_values=observed, ownership_verified_at=domain.ownership_verified_at)


@router.patch("/{domain_id}/status", response_model=DomainRead)
def change_domain_status(tenant_id: UUID, domain_id: UUID, payload: DomainStatusUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    if payload.status == DomainStatus.verified and domain.ownership_verified_at is None:
        raise HTTPException(status_code=409, detail="Ownership verification is required before verified status")
    if domain.status == DomainStatus.archived:
        raise HTTPException(status_code=409, detail="Archived domains cannot change status")
    previous = domain.status.value
    domain.status = payload.status
    add_domain_event(db, domain, current.id, "domain.status_changed", {"from": previous, "to": payload.status.value})
    _audit(db, tenant_id, current, "domain.status_change", domain, {"from": previous, "to": payload.status.value})
    db.commit()
    db.refresh(domain)
    return domain


@router.delete("/{domain_id}", response_model=DomainRead)
def archive_domain(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    if domain.status != DomainStatus.archived:
        domain.status = DomainStatus.archived
        add_domain_event(db, domain, current.id, "domain.archived")
        _audit(db, tenant_id, current, "domain.archive", domain)
        db.commit()
        db.refresh(domain)
    return domain


@router.delete("/{domain_id}/release", status_code=status.HTTP_204_NO_CONTENT)
def release_domain_claim(
    tenant_id: UUID,
    domain_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    domain = _domain_or_404(db, tenant_id, domain_id)
    if domain.status != DomainStatus.archived:
        raise HTTPException(status_code=409, detail="Domain must be archived before its global claim can be released")

    blockers = _release_blockers(db, domain)
    if blockers:
        raise HTTPException(
            status_code=409,
            detail=(
                "Permanent release is blocked because the domain still has a managed service lifecycle: "
                + ", ".join(blockers)
                + ". Deprovision these resources before releasing the global claim."
            ),
        )

    _audit(db, tenant_id, current, "domain.release", domain, {"ascii_name": domain.ascii_name, "clean_release": True})
    db.delete(domain)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{domain_id}/events", response_model=list[DomainEventRead])
def domain_events(tenant_id: UUID, domain_id: UUID, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    _domain_or_404(db, tenant_id, domain_id)
    return db.scalars(select(DomainEvent).where(DomainEvent.domain_id == domain_id).order_by(DomainEvent.created_at.desc()).limit(limit)).all()


@router.get("/{domain_id}/verification-attempts", response_model=list[DomainVerificationAttemptRead])
def verification_attempts(tenant_id: UUID, domain_id: UUID, limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    _domain_or_404(db, tenant_id, domain_id)
    return db.scalars(
        select(DomainVerificationAttempt)
        .where(DomainVerificationAttempt.domain_id == domain_id)
        .order_by(DomainVerificationAttempt.created_at.desc())
        .limit(limit)
    ).all()


@router.get("/{domain_id}/readiness", response_model=DomainReadiness)
def domain_readiness(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    verified = domain.ownership_verified_at is not None and domain.status == DomainStatus.verified
    pending_step = "Complete TXT ownership verification" if domain.verification_method == DomainVerificationMethod.txt.value else "Prepare DNS, delegate both Ithute nameservers, then verify"
    return DomainReadiness(
        domain_id=domain.id,
        ownership_verified=verified,
        domain_status=domain.status,
        dns_mode=domain.dns_mode,
        ready_for_powerdns=verified and domain.dns_mode.value == "platform",
        required_nameservers=[settings.nameserver_1, settings.nameserver_2],
        next_phase="Phase 4: create PowerDNS zone and verify nameserver delegation" if verified else pending_step,
    )
