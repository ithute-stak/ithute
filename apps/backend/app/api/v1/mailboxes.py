import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, User
from app.models.domains import Domain, DomainStatus
from app.models.mail import DistributionGroup, DistributionGroupMember, MailAlias, Mailbox, MailboxStatus
from app.services.billing import require_entitlement
from app.services.mailboxes import hash_mailbox_password, mailbox_address, normalize_destination, normalize_local_part, utcnow

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["mailboxes"])


class MailboxCreate(BaseModel):
    domain_id: UUID
    local_part: str
    password: str
    display_name: str | None = Field(default=None, max_length=150)
    quota_bytes: int = Field(default=5 * 1024**3, ge=100 * 1024**2, le=10 * 1024**4)


class MailboxUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=150)
    quota_bytes: int | None = Field(default=None, ge=100 * 1024**2, le=10 * 1024**4)


class PasswordChange(BaseModel):
    password: str


class AliasCreate(BaseModel):
    domain_id: UUID
    local_part: str
    destination_address: str


class GroupCreate(BaseModel):
    domain_id: UUID
    local_part: str
    display_name: str | None = Field(default=None, max_length=150)


class GroupMemberCreate(BaseModel):
    destination_address: str


def _permission(tenant_id: UUID, permission: str, db: Session, current: User) -> None:
    require_tenant_permission(tenant_id, permission, db, current)


def _mail_domain(db: Session, tenant_id: UUID, domain_id: UUID) -> Domain:
    domain = db.scalar(select(Domain).where(Domain.id == domain_id, Domain.tenant_id == tenant_id))
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    if domain.status != DomainStatus.verified or not domain.mail_enabled:
        raise HTTPException(status_code=409, detail="Domain must be verified and mail-enabled")
    return domain


def _mailbox(db: Session, tenant_id: UUID, mailbox_id: UUID) -> Mailbox:
    item = db.scalar(select(Mailbox).where(Mailbox.id == mailbox_id, Mailbox.tenant_id == tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    return item


def _audit(db: Session, tenant_id: UUID, current: User, action: str, resource_type: str, resource_id: str, metadata: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_user_id=current.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


def _mailbox_json(item: Mailbox) -> dict:
    return {
        "id": str(item.id), "tenant_id": str(item.tenant_id), "domain_id": str(item.domain_id),
        "local_part": item.local_part, "address": item.address, "display_name": item.display_name,
        "quota_bytes": item.quota_bytes, "status": item.status.value,
        "password_changed_at": item.password_changed_at, "created_at": item.created_at, "updated_at": item.updated_at,
    }


@router.post("/mailboxes", status_code=201)
def create_mailbox(tenant_id: UUID, payload: MailboxCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    domain = _mail_domain(db, tenant_id, payload.domain_id)
    try:
        require_entitlement(db, tenant_id, "mailbox", requested_storage_bytes=payload.quota_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        local = normalize_local_part(payload.local_part)
        address = mailbox_address(local, domain.ascii_name)
        password_hash = hash_mailbox_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if db.scalar(select(Mailbox).where(Mailbox.address == address)) or db.scalar(select(DistributionGroup).where(DistributionGroup.address == address)):
        raise HTTPException(status_code=409, detail="Address is already in use")
    item = Mailbox(
        tenant_id=tenant_id, domain_id=domain.id, local_part=local, address=address,
        display_name=payload.display_name, password_hash=password_hash, quota_bytes=payload.quota_bytes,
        created_by_user_id=current.id,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mailbox address already exists") from exc
    _audit(db, tenant_id, current, "mailbox.create", "mailbox", str(item.id), {"address": address})
    db.commit()
    db.refresh(item)
    return _mailbox_json(item)


@router.get("/mailboxes")
def list_mailboxes(tenant_id: UUID, domain_id: UUID | None = None, q: str | None = None, status_filter: MailboxStatus | None = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.read", db, current)
    stmt = select(Mailbox).where(Mailbox.tenant_id == tenant_id)
    if domain_id:
        stmt = stmt.where(Mailbox.domain_id == domain_id)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Mailbox.address).like(needle), func.lower(func.coalesce(Mailbox.display_name, "")).like(needle)))
    if status_filter:
        stmt = stmt.where(Mailbox.status == status_filter)
    items = db.scalars(stmt.order_by(Mailbox.address)).all()
    return {"items": [_mailbox_json(item) for item in items], "total": len(items)}


@router.get("/mailboxes/{mailbox_id}")
def get_mailbox(tenant_id: UUID, mailbox_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.read", db, current)
    return _mailbox_json(_mailbox(db, tenant_id, mailbox_id))


@router.patch("/mailboxes/{mailbox_id}")
def update_mailbox(tenant_id: UUID, mailbox_id: UUID, payload: MailboxUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    item = _mailbox(db, tenant_id, mailbox_id)
    if item.status == MailboxStatus.archived:
        raise HTTPException(status_code=409, detail="Archived mailbox is read-only")
    if payload.display_name is not None:
        item.display_name = payload.display_name
    if payload.quota_bytes is not None:
        delta = max(0, payload.quota_bytes - item.quota_bytes)
        if delta:
            try:
                require_entitlement(db, tenant_id, "storage", requested_storage_bytes=delta)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        item.quota_bytes = payload.quota_bytes
    _audit(db, tenant_id, current, "mailbox.update", "mailbox", str(item.id))
    db.commit()
    db.refresh(item)
    return _mailbox_json(item)


@router.post("/mailboxes/{mailbox_id}/password")
def change_mailbox_password(tenant_id: UUID, mailbox_id: UUID, payload: PasswordChange, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    item = _mailbox(db, tenant_id, mailbox_id)
    if item.status == MailboxStatus.archived:
        raise HTTPException(status_code=409, detail="Archived mailbox is read-only")
    try:
        item.password_hash = hash_mailbox_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item.password_changed_at = utcnow()
    _audit(db, tenant_id, current, "mailbox.password_change", "mailbox", str(item.id))
    db.commit()
    return {"id": str(item.id), "password_changed_at": item.password_changed_at}


@router.post("/mailboxes/{mailbox_id}/suspend")
def suspend_mailbox(tenant_id: UUID, mailbox_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    item = _mailbox(db, tenant_id, mailbox_id)
    if item.status == MailboxStatus.archived:
        raise HTTPException(status_code=409, detail="Archived mailbox cannot be suspended")
    item.status = MailboxStatus.suspended
    _audit(db, tenant_id, current, "mailbox.suspend", "mailbox", str(item.id))
    db.commit()
    db.refresh(item)
    return _mailbox_json(item)


@router.post("/mailboxes/{mailbox_id}/restore")
def restore_mailbox(tenant_id: UUID, mailbox_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    item = _mailbox(db, tenant_id, mailbox_id)
    if item.status == MailboxStatus.archived:
        raise HTTPException(status_code=409, detail="Archived mailbox cannot be restored")
    item.status = MailboxStatus.active
    _audit(db, tenant_id, current, "mailbox.restore", "mailbox", str(item.id))
    db.commit()
    db.refresh(item)
    return _mailbox_json(item)


@router.delete("/mailboxes/{mailbox_id}")
def archive_mailbox(tenant_id: UUID, mailbox_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    item = _mailbox(db, tenant_id, mailbox_id)
    item.status = MailboxStatus.archived
    _audit(db, tenant_id, current, "mailbox.archive", "mailbox", str(item.id))
    db.commit()
    db.refresh(item)
    return _mailbox_json(item)


@router.post("/aliases", status_code=201)
def create_alias(tenant_id: UUID, payload: AliasCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    domain = _mail_domain(db, tenant_id, payload.domain_id)
    try:
        source = mailbox_address(payload.local_part, domain.ascii_name)
        destination = normalize_destination(payload.destination_address)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if source == destination:
        raise HTTPException(status_code=422, detail="Alias cannot point to itself")
    if not db.scalar(select(Mailbox).where(Mailbox.tenant_id == tenant_id, Mailbox.address == destination, Mailbox.status == MailboxStatus.active)) and not db.scalar(select(DistributionGroup).where(DistributionGroup.tenant_id == tenant_id, DistributionGroup.address == destination, DistributionGroup.active.is_(True))):
        raise HTTPException(status_code=409, detail="Alias destination must be an active mailbox or group in this tenant")
    if db.scalar(select(Mailbox).where(Mailbox.address == source)) or db.scalar(select(DistributionGroup).where(DistributionGroup.address == source)):
        raise HTTPException(status_code=409, detail="Alias source address is already in use")
    item = MailAlias(tenant_id=tenant_id, domain_id=domain.id, source_address=source, destination_address=destination, created_by_user_id=current.id)
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Alias route already exists") from exc
    _audit(db, tenant_id, current, "alias.create", "mail_alias", str(item.id), {"source": source, "destination": destination})
    db.commit()
    db.refresh(item)
    return {"id": str(item.id), "source_address": item.source_address, "destination_address": item.destination_address, "active": item.active}


@router.get("/aliases")
def list_aliases(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.read", db, current)
    items = db.scalars(select(MailAlias).where(MailAlias.tenant_id == tenant_id).order_by(MailAlias.source_address)).all()
    return {"items": [{"id": str(x.id), "source_address": x.source_address, "destination_address": x.destination_address, "active": x.active} for x in items], "total": len(items)}


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(tenant_id: UUID, alias_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    item = db.scalar(select(MailAlias).where(MailAlias.id == alias_id, MailAlias.tenant_id == tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="Alias not found")
    _audit(db, tenant_id, current, "alias.delete", "mail_alias", str(item.id))
    db.delete(item)
    db.commit()


@router.post("/groups", status_code=201)
def create_group(tenant_id: UUID, payload: GroupCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    domain = _mail_domain(db, tenant_id, payload.domain_id)
    try:
        local = normalize_local_part(payload.local_part)
        address = mailbox_address(local, domain.ascii_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if db.scalar(select(Mailbox).where(Mailbox.address == address)) or db.scalar(select(DistributionGroup).where(DistributionGroup.address == address)):
        raise HTTPException(status_code=409, detail="Address is already in use")
    item = DistributionGroup(tenant_id=tenant_id, domain_id=domain.id, local_part=local, address=address, display_name=payload.display_name, created_by_user_id=current.id)
    db.add(item)
    db.flush()
    _audit(db, tenant_id, current, "group.create", "distribution_group", str(item.id), {"address": address})
    db.commit()
    db.refresh(item)
    return {"id": str(item.id), "address": item.address, "display_name": item.display_name, "active": item.active, "members": []}


@router.get("/groups")
def list_groups(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.read", db, current)
    items = db.scalars(select(DistributionGroup).where(DistributionGroup.tenant_id == tenant_id).order_by(DistributionGroup.address)).all()
    return {"items": [{"id": str(x.id), "address": x.address, "display_name": x.display_name, "active": x.active, "members": [m.destination_address for m in x.members]} for x in items], "total": len(items)}


@router.post("/groups/{group_id}/members", status_code=201)
def add_group_member(tenant_id: UUID, group_id: UUID, payload: GroupMemberCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    group = db.scalar(select(DistributionGroup).where(DistributionGroup.id == group_id, DistributionGroup.tenant_id == tenant_id))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    try:
        destination = normalize_destination(payload.destination_address)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if destination == group.address:
        raise HTTPException(status_code=422, detail="Group cannot contain itself")
    if not db.scalar(select(Mailbox).where(Mailbox.tenant_id == tenant_id, Mailbox.address == destination, Mailbox.status == MailboxStatus.active)):
        raise HTTPException(status_code=409, detail="Group member must be an active mailbox in this tenant")
    member = DistributionGroupMember(group_id=group.id, destination_address=destination)
    db.add(member)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Group member already exists") from exc
    _audit(db, tenant_id, current, "group.member_add", "distribution_group", str(group.id), {"destination": destination})
    db.commit()
    db.refresh(member)
    return {"id": str(member.id), "destination_address": member.destination_address}


@router.get("/groups/{group_id}/members")
def list_group_members(tenant_id: UUID, group_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.read", db, current)
    group = db.scalar(select(DistributionGroup).where(DistributionGroup.id == group_id, DistributionGroup.tenant_id == tenant_id))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    rows = db.scalars(select(DistributionGroupMember).where(DistributionGroupMember.group_id == group_id).order_by(DistributionGroupMember.destination_address)).all()
    return {"items": [{"id": str(x.id), "destination_address": x.destination_address} for x in rows], "total": len(rows)}


@router.delete("/groups/{group_id}/members/{member_id}", status_code=204)
def delete_group_member(tenant_id: UUID, group_id: UUID, member_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    group = db.scalar(select(DistributionGroup).where(DistributionGroup.id == group_id, DistributionGroup.tenant_id == tenant_id))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    member = db.scalar(select(DistributionGroupMember).where(DistributionGroupMember.id == member_id, DistributionGroupMember.group_id == group_id))
    if not member:
        raise HTTPException(status_code=404, detail="Group member not found")
    _audit(db, tenant_id, current, "group.member_delete", "distribution_group", str(group.id), {"destination": member.destination_address})
    db.delete(member)
    db.commit()


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(tenant_id: UUID, group_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _permission(tenant_id, "mail.manage", db, current)
    group = db.scalar(select(DistributionGroup).where(DistributionGroup.id == group_id, DistributionGroup.tenant_id == tenant_id))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _audit(db, tenant_id, current, "group.delete", "distribution_group", str(group.id), {"address": group.address})
    db.delete(group)
    db.commit()
