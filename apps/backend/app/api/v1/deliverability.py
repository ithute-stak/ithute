import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import AuditLog, DkimKey, User
from app.models.domains import Domain, DomainStatus
from app.services.deliverability import (
    deliverability_readiness,
    generate_dkim_material,
    infrastructure_readiness,
    normalize_selector,
    recommended_records,
)
from app.services.dkim_sync import sync_active_dkim_keys

router = APIRouter(prefix="/tenants/{tenant_id}/domains/{domain_id}/deliverability", tags=["deliverability"])


class DkimCreate(BaseModel):
    selector: str = Field(default="s1", min_length=1, max_length=63)


class DkimRotate(BaseModel):
    selector: str = Field(min_length=1, max_length=63)


def _domain(db: Session, tenant_id: UUID, domain_id: UUID) -> Domain:
    domain = db.scalar(select(Domain).where(Domain.id == domain_id, Domain.tenant_id == tenant_id))
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    if domain.status != DomainStatus.verified or not domain.mail_enabled:
        raise HTTPException(status_code=409, detail="Domain must be verified and mail-enabled")
    return domain


def _active_key(db: Session, tenant_id: UUID, domain_id: UUID) -> DkimKey | None:
    return db.scalar(select(DkimKey).where(DkimKey.tenant_id == tenant_id, DkimKey.domain_id == domain_id, DkimKey.active.is_(True)).order_by(DkimKey.created_at.desc()))


def _audit(db: Session, tenant_id: UUID, current: User, action: str, resource_id: str, metadata: dict | None = None) -> None:
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action=action, resource_type="deliverability", resource_id=resource_id, metadata_json=json.dumps(metadata or {}, sort_keys=True)))


def _key_json(domain: Domain, key: DkimKey) -> dict:
    return {
        "id": str(key.id),
        "selector": key.selector,
        "algorithm": key.algorithm,
        "active": key.active,
        "dns_name": f"{key.selector}._domainkey.{domain.ascii_name}",
        "dns_value": f"v=DKIM1; k=rsa; p={key.public_key_b64}",
        "created_at": key.created_at,
        "rotated_at": key.rotated_at,
    }


def _sync_or_fail(db: Session) -> None:
    try:
        sync_active_dkim_keys(db)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="DKIM key was stored but Rspamd signing synchronization failed") from exc


@router.post("/dkim", status_code=201)
def create_dkim(tenant_id: UUID, domain_id: UUID, payload: DkimCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    domain = _domain(db, tenant_id, domain_id)
    try:
        selector = normalize_selector(payload.selector)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if db.scalar(select(DkimKey).where(DkimKey.domain_id == domain.id, DkimKey.selector == selector)):
        raise HTTPException(status_code=409, detail="DKIM selector already exists for this domain")
    encrypted, public = generate_dkim_material()
    has_active = _active_key(db, tenant_id, domain.id) is not None
    key = DkimKey(tenant_id=tenant_id, domain_id=domain.id, selector=selector, public_key_b64=public, private_key_encrypted=encrypted, active=not has_active, created_by_user_id=current.id)
    db.add(key); db.flush()
    _audit(db, tenant_id, current, "deliverability.dkim.create", str(key.id), {"domain": domain.ascii_name, "selector": selector, "active": key.active})
    db.commit(); db.refresh(key)
    if key.active:
        _sync_or_fail(db)
    return _key_json(domain, key)


@router.post("/dkim/{key_id}/rotate", status_code=201)
def rotate_dkim(tenant_id: UUID, domain_id: UUID, key_id: UUID, payload: DkimRotate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Stage a new selector/key without changing the live signer.

    The returned TXT record must be published and allowed to propagate before
    calling the activation endpoint. This avoids overwriting a live selector.
    """
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    domain = _domain(db, tenant_id, domain_id)
    current_key = db.scalar(select(DkimKey).where(DkimKey.id == key_id, DkimKey.domain_id == domain.id, DkimKey.tenant_id == tenant_id))
    if not current_key:
        raise HTTPException(status_code=404, detail="DKIM key not found")
    try:
        selector = normalize_selector(payload.selector)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if selector == current_key.selector or db.scalar(select(DkimKey).where(DkimKey.domain_id == domain.id, DkimKey.selector == selector)):
        raise HTTPException(status_code=409, detail="Rotation requires a new unused DKIM selector")
    encrypted, public = generate_dkim_material()
    staged = DkimKey(tenant_id=tenant_id, domain_id=domain.id, selector=selector, public_key_b64=public, private_key_encrypted=encrypted, active=False, created_by_user_id=current.id)
    db.add(staged); db.flush()
    _audit(db, tenant_id, current, "deliverability.dkim.rotation.stage", str(staged.id), {"domain": domain.ascii_name, "from_selector": current_key.selector, "to_selector": selector})
    db.commit(); db.refresh(staged)
    return {**_key_json(domain, staged), "rotation_state": "staged", "next_step": "Publish the returned DKIM TXT record, wait for DNS propagation, then activate this key."}


@router.post("/dkim/{key_id}/activate")
def activate_dkim(tenant_id: UUID, domain_id: UUID, key_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    domain = _domain(db, tenant_id, domain_id)
    key = db.scalar(select(DkimKey).where(DkimKey.id == key_id, DkimKey.domain_id == domain.id, DkimKey.tenant_id == tenant_id))
    if not key:
        raise HTTPException(status_code=404, detail="DKIM key not found")
    if key.active:
        return {**_key_json(domain, key), "rotation_state": "active"}
    previous = db.scalars(select(DkimKey).where(DkimKey.domain_id == domain.id, DkimKey.active.is_(True))).all()
    for existing in previous:
        existing.active = False
        existing.rotated_at = datetime.now(timezone.utc)
    key.active = True
    _audit(db, tenant_id, current, "deliverability.dkim.rotation.activate", str(key.id), {"domain": domain.ascii_name, "selector": key.selector, "retired_selectors": [row.selector for row in previous]})
    db.commit(); db.refresh(key)
    _sync_or_fail(db)
    return {**_key_json(domain, key), "rotation_state": "active", "retire_after": "Keep the previous selector TXT record published for at least its DNS TTL overlap window."}


@router.post("/dkim/sync")
def sync_dkim(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    _domain(db, tenant_id, domain_id)
    try:
        count = sync_active_dkim_keys(db)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Rspamd DKIM synchronization failed") from exc
    _audit(db, tenant_id, current, "deliverability.dkim.sync", str(domain_id), {"active_domains": count})
    db.commit()
    return {"synchronized_domains": count}


@router.get("/records")
def records(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    domain = _domain(db, tenant_id, domain_id)
    key = _active_key(db, tenant_id, domain.id)
    if not key:
        raise HTTPException(status_code=409, detail="Generate an active DKIM key first")
    return {"domain": domain.ascii_name, "mail_hostname": settings.mail_hostname, "records": recommended_records(domain.ascii_name, settings.mail_hostname, key.selector, key.public_key_b64)}


@router.get("/infrastructure-readiness")
def infrastructure(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    domain = _domain(db, tenant_id, domain_id)
    result = infrastructure_readiness(settings.mail_hostname, settings.mail_public_ip)
    result.update({"domain": domain.ascii_name})
    return result


@router.get("/readiness")
def readiness(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    domain = _domain(db, tenant_id, domain_id)
    key = _active_key(db, tenant_id, domain.id)
    infrastructure_result = infrastructure_readiness(settings.mail_hostname, settings.mail_public_ip)
    if not key:
        return {"ready": False, "checks": {"mx": False, "spf": False, "dkim": False, "dmarc": False}, "infrastructure": infrastructure_result, "detail": "Generate an active DKIM key first"}
    result = deliverability_readiness(domain.ascii_name, settings.mail_hostname, key.selector, key.public_key_b64)
    result.update({"domain": domain.ascii_name, "mail_hostname": settings.mail_hostname, "selector": key.selector, "infrastructure": infrastructure_result})
    result["ready"] = bool(result["ready"] and infrastructure_result["ready"])
    return result
