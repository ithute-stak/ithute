import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_membership, require_tenant_permission
from app.core.config import settings
from app.core.security import generate_api_key, hash_password, hash_token
from app.db.session import get_db
from app.models import (
    ApiKey,
    AuditLog,
    Invitation,
    MembershipRole,
    MembershipStatus,
    Tenant,
    TenantMembership,
    User,
)
from app.schemas.identity import (
    ApiKeyCreate,
    ApiKeyOut,
    InvitationAccept,
    InviteCreate,
    InviteOut,
    MembershipOut,
    MembershipUpdate,
    MyMembershipOut,
)
from app.services.billing import require_entitlement

router = APIRouter(tags=["identity"])


def _ensure_tenant(tenant_id: UUID, db: Session) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _require_identity_admin(tenant_id: UUID, db: Session, current: User) -> None:
    _ensure_tenant(tenant_id, db)
    require_tenant_permission(tenant_id, "identity.manage", db, current)


def _active_admin_count(tenant_id: UUID, db: Session) -> int:
    return int(db.scalar(
        select(func.count(TenantMembership.id)).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.role == MembershipRole.tenant_admin,
            TenantMembership.status == MembershipStatus.active,
        )
    ) or 0)


def _membership_out(membership: TenantMembership, user: User) -> MembershipOut:
    return MembershipOut(
        id=str(membership.id),
        tenant_id=str(membership.tenant_id),
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        status=membership.status,
    )


@router.get("/me/memberships", response_model=list[MyMembershipOut])
def my_memberships(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(TenantMembership.user_id == current.id)
        .order_by(Tenant.name)
    ).all()
    return [
        MyMembershipOut(
            membership_id=str(m.id),
            tenant_id=str(t.id),
            tenant_name=t.name,
            tenant_slug=t.slug,
            tenant_status=t.status.value,
            role=m.role,
            status=m.status,
        )
        for m, t in rows
    ]


@router.get("/tenants/{tenant_id}/members", response_model=list[MembershipOut])
def list_members(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _ensure_tenant(tenant_id, db)
    if not current.is_platform_owner:
        require_tenant_membership(tenant_id, db, current)
    rows = db.execute(
        select(TenantMembership, User)
        .join(User, User.id == TenantMembership.user_id)
        .where(TenantMembership.tenant_id == tenant_id)
        .order_by(User.full_name)
    ).all()
    return [_membership_out(m, u) for m, u in rows]


@router.patch("/tenants/{tenant_id}/members/{membership_id}", response_model=MembershipOut)
def update_membership(
    tenant_id: UUID,
    membership_id: UUID,
    payload: MembershipUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _require_identity_admin(tenant_id, db, current)
    membership = db.get(TenantMembership, membership_id)
    if not membership or membership.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    if payload.role is None and payload.status is None:
        raise HTTPException(status_code=400, detail="No membership changes supplied")
    removing_active_admin = (
        membership.role == MembershipRole.tenant_admin
        and membership.status == MembershipStatus.active
        and (
            (payload.role is not None and payload.role != MembershipRole.tenant_admin)
            or (payload.status is not None and payload.status != MembershipStatus.active)
        )
    )
    if removing_active_admin and _active_admin_count(tenant_id, db) <= 1:
        raise HTTPException(status_code=409, detail="Tenant must retain at least one active tenant admin")
    if membership.user_id == current.id and payload.status == MembershipStatus.suspended:
        raise HTTPException(status_code=409, detail="Cannot suspend your own membership")
    if payload.role is not None:
        membership.role = payload.role
    if payload.status is not None:
        membership.status = payload.status
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_user_id=current.id,
        action="membership.update",
        resource_type="membership",
        resource_id=str(membership.id),
        metadata_json=json.dumps({"role": membership.role.value, "status": membership.status.value}),
    ))
    db.commit()
    return _membership_out(membership, db.get(User, membership.user_id))


@router.delete("/tenants/{tenant_id}/members/{membership_id}", status_code=204)
def suspend_member(tenant_id: UUID, membership_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_identity_admin(tenant_id, db, current)
    membership = db.get(TenantMembership, membership_id)
    if not membership or membership.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    if membership.user_id == current.id:
        raise HTTPException(status_code=409, detail="Cannot suspend your own membership")
    if membership.role == MembershipRole.tenant_admin and membership.status == MembershipStatus.active and _active_admin_count(tenant_id, db) <= 1:
        raise HTTPException(status_code=409, detail="Tenant must retain at least one active tenant admin")
    membership.status = MembershipStatus.suspended
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="membership.suspend", resource_type="membership", resource_id=str(membership.id)))
    db.commit()


@router.get("/tenants/{tenant_id}/invitations", response_model=list[InviteOut])
def list_invitations(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_identity_admin(tenant_id, db, current)
    rows = db.scalars(select(Invitation).where(Invitation.tenant_id == tenant_id).order_by(Invitation.created_at.desc())).all()
    return [InviteOut(id=str(x.id), tenant_id=str(x.tenant_id), email=x.email, role=x.role, expires_at=x.expires_at.isoformat(), accepted_at=x.accepted_at.isoformat() if x.accepted_at else None) for x in rows]


@router.post("/tenants/{tenant_id}/invitations", response_model=InviteOut, status_code=201)
def create_invitation(tenant_id: UUID, payload: InviteCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_identity_admin(tenant_id, db, current)
    email = payload.email.lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user:
        existing_membership = db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == existing_user.id))
        if existing_membership:
            raise HTTPException(status_code=409, detail="User already belongs to tenant")
    open_invite = db.scalar(select(Invitation).where(
        Invitation.tenant_id == tenant_id,
        Invitation.email == email,
        Invitation.accepted_at.is_(None),
        Invitation.expires_at > datetime.now(timezone.utc),
    ))
    if open_invite:
        raise HTTPException(status_code=409, detail="An active invitation already exists for this email")
    raw = secrets.token_urlsafe(40)
    invite = Invitation(
        tenant_id=tenant_id,
        email=email,
        role=payload.role,
        token_hash=hash_token(raw),
        invited_by_user_id=current.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.invitation_expire_hours),
    )
    db.add(invite)
    db.flush()
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="invitation.create", resource_type="invitation", resource_id=str(invite.id)))
    db.commit()
    exposed_token = None if settings.environment.lower() == "production" else raw
    return InviteOut(id=str(invite.id), tenant_id=str(tenant_id), email=invite.email, role=invite.role, expires_at=invite.expires_at.isoformat(), token=exposed_token)


@router.delete("/tenants/{tenant_id}/invitations/{invitation_id}", status_code=204)
def cancel_invitation(tenant_id: UUID, invitation_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_identity_admin(tenant_id, db, current)
    invite = db.get(Invitation, invitation_id)
    if not invite or invite.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Accepted invitation cannot be cancelled")
    db.delete(invite)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="invitation.cancel", resource_type="invitation", resource_id=str(invitation_id)))
    db.commit()


@router.post("/invitations/accept", response_model=MembershipOut)
def accept_invitation(payload: InvitationAccept, db: Session = Depends(get_db)):
    invite = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(payload.token)))
    now = datetime.now(timezone.utc)
    if not invite or invite.accepted_at is not None or invite.expires_at <= now:
        raise HTTPException(status_code=400, detail="Invitation invalid or expired")
    user = db.scalar(select(User).where(User.email == invite.email))
    if not user:
        user = User(email=invite.email, full_name=payload.full_name, password_hash=hash_password(payload.password), email_verified_at=now)
        db.add(user)
        db.flush()
    elif not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    else:
        user.email_verified_at = user.email_verified_at or now
    if db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == invite.tenant_id, TenantMembership.user_id == user.id)):
        raise HTTPException(status_code=409, detail="User already belongs to tenant")
    membership = TenantMembership(tenant_id=invite.tenant_id, user_id=user.id, role=invite.role)
    db.add(membership)
    db.flush()
    invite.accepted_at = now
    db.add(AuditLog(tenant_id=invite.tenant_id, actor_user_id=user.id, action="invitation.accept", resource_type="membership", resource_id=str(membership.id)))
    db.commit()
    return _membership_out(membership, user)


def _api_key_out(key: ApiKey, raw: str | None = None) -> ApiKeyOut:
    return ApiKeyOut(
        id=str(key.id),
        tenant_id=str(key.tenant_id),
        name=key.name,
        prefix=key.prefix,
        scopes=json.loads(key.scopes or "[]"),
        created_at=key.created_at.isoformat(),
        expires_at=key.expires_at.isoformat() if key.expires_at else None,
        revoked=key.revoked_at is not None,
        key=raw,
    )


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(tenant_id: UUID | None = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    stmt = select(ApiKey).where(ApiKey.owner_user_id == current.id, ApiKey.tenant_id.is_not(None))
    if tenant_id:
        require_tenant_membership(tenant_id, db, current)
        stmt = stmt.where(ApiKey.tenant_id == tenant_id)
    rows = db.scalars(stmt.order_by(ApiKey.created_at.desc())).all()
    return [_api_key_out(x) for x in rows]


@router.post("/api-keys", response_model=ApiKeyOut, status_code=201)
def create_api_key(payload: ApiKeyCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_membership(payload.tenant_id, db, current)
    try:
        require_entitlement(db, payload.tenant_id, "api_key")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raw, prefix, digest = generate_api_key()
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None
    key = ApiKey(tenant_id=payload.tenant_id, owner_user_id=current.id, name=payload.name, prefix=prefix, key_hash=digest, scopes=json.dumps(sorted(set(payload.scopes))), expires_at=expires_at)
    db.add(key)
    db.flush()
    db.add(AuditLog(tenant_id=payload.tenant_id, actor_user_id=current.id, action="api_key.create", resource_type="api_key", resource_id=str(key.id)))
    db.commit()
    db.refresh(key)
    return _api_key_out(key, raw)


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key(key_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    key = db.get(ApiKey, key_id)
    if not key or key.owner_user_id != current.id:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(timezone.utc)
        db.add(AuditLog(tenant_id=key.tenant_id, actor_user_id=current.id, action="api_key.revoke", resource_type="api_key", resource_id=str(key.id)))
        db.commit()
