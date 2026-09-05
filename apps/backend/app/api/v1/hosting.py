import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.models import (
    AuditLog,
    BillingPlan,
    DomainOrder,
    GroupwareCredential,
    MailNode,
    Mailbox,
    MailboxStatus,
    MembershipRole,
    ResellerAccount,
    ResellerCustomer,
    SubscriptionStatus,
    Tenant,
    TenantMembership,
    User,
    WhiteLabelBrand,
)
from app.services.billing import assign_subscription, ensure_default_plans
from app.services.commercial_providers import (
    ProviderConfigurationError,
    ProviderRequestError,
    opensrs_configured,
    opensrs_lookup,
    opensrs_register,
)

router = APIRouter(tags=["hosting-company"])


class ResellerCreate(BaseModel):
    max_customers: int = Field(default=100, ge=1, le=100000)
    discount_bps: int = Field(default=0, ge=0, le=9000)


class BrandUpdate(BaseModel):
    brand_name: str = Field(min_length=2, max_length=120)
    support_email: EmailStr | None = None
    logo_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    custom_hostname: str | None = Field(default=None, max_length=253)


class ResellerCustomerCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=150)
    company_slug: str | None = Field(default=None, max_length=80)
    admin_name: str = Field(min_length=2, max_length=150)
    admin_email: EmailStr
    admin_password: str = Field(min_length=12, max_length=256)
    plan_code: str = Field(default="starter", max_length=50)


class DomainLookup(BaseModel):
    domain_name: str = Field(min_length=4, max_length=253)


class DomainRegister(BaseModel):
    domain_name: str = Field(min_length=4, max_length=253)
    years: int = Field(default=1, ge=1, le=10)
    registrant_username: str = Field(min_length=3, max_length=20)
    registrant_password: str = Field(min_length=10, max_length=20)
    owner_name: str = Field(min_length=2, max_length=120)
    owner_email: EmailStr
    owner_phone: str = Field(min_length=5, max_length=40)
    owner_address: str = Field(min_length=3, max_length=200)
    owner_city: str = Field(min_length=2, max_length=100)
    owner_country: str = Field(default="LS", min_length=2, max_length=2)
    owner_postal_code: str = Field(default="100", max_length=20)


class GroupwareCreate(BaseModel):
    mailbox_id: UUID
    password: str = Field(min_length=12, max_length=256)


class MailNodeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern=r"^(smtp|imap|combined|dns|edge)$")
    region: str = Field(default="lesotho", max_length=80)
    public_ip: str | None = Field(default=None, max_length=64)
    hostname: str = Field(min_length=3, max_length=253)
    weight: int = Field(default=100, ge=0, le=1000)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:80]


def _reseller(db: Session, tenant_id: UUID) -> ResellerAccount:
    row = db.scalar(select(ResellerAccount).where(ResellerAccount.tenant_id == tenant_id))
    if row is None or row.status != "active":
        raise HTTPException(status_code=403, detail="Active reseller account required")
    return row


def _sync_groupware_auth(db: Session) -> None:
    path = Path(settings.groupware_auth_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = db.scalars(select(GroupwareCredential).where(GroupwareCredential.active.is_(True)).order_by(GroupwareCredential.username)).all()
    content = "\n".join(f"{x.username}:{x.password_hash}" for x in rows)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")


@router.post("/platform/resellers/{tenant_id}", status_code=201)
def create_reseller(tenant_id: UUID, payload: ResellerCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    row = db.scalar(select(ResellerAccount).where(ResellerAccount.tenant_id == tenant_id))
    if row is None:
        row = ResellerAccount(tenant_id=tenant_id)
        db.add(row)
    row.status = "active"
    row.max_customers = payload.max_customers
    row.discount_bps = payload.discount_bps
    db.add(AuditLog(actor_user_id=current.id, tenant_id=tenant_id, action="reseller.enable", resource_type="reseller_account", resource_id=str(row.id) if row.id else None))
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "tenant_id": str(row.tenant_id), "status": row.status, "max_customers": row.max_customers, "discount_bps": row.discount_bps}


@router.get("/tenants/{tenant_id}/reseller")
def reseller_summary(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    row = _reseller(db, tenant_id)
    count = db.scalar(select(func.count(ResellerCustomer.id)).where(ResellerCustomer.reseller_id == row.id)) or 0
    return {"id": str(row.id), "status": row.status, "max_customers": row.max_customers, "discount_bps": row.discount_bps, "customer_count": int(count)}


@router.get("/tenants/{tenant_id}/reseller/brand")
def get_brand(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    reseller = _reseller(db, tenant_id)
    row = db.scalar(select(WhiteLabelBrand).where(WhiteLabelBrand.reseller_id == reseller.id))
    if row is None:
        return {"brand_name": settings.app_name, "support_email": None, "logo_url": None, "primary_color": None, "custom_hostname": None}
    return {"brand_name": row.brand_name, "support_email": row.support_email, "logo_url": row.logo_url, "primary_color": row.primary_color, "custom_hostname": row.custom_hostname}


@router.put("/tenants/{tenant_id}/reseller/brand")
def update_brand(tenant_id: UUID, payload: BrandUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    reseller = _reseller(db, tenant_id)
    row = db.scalar(select(WhiteLabelBrand).where(WhiteLabelBrand.reseller_id == reseller.id))
    if row is None:
        row = WhiteLabelBrand(reseller_id=reseller.id, brand_name=payload.brand_name)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, str(value) if key == "support_email" and value is not None else value)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="reseller.brand.update", resource_type="white_label_brand", resource_id=str(row.id) if row.id else None))
    db.commit()
    return {"saved": True}


@router.post("/tenants/{tenant_id}/reseller/customers", status_code=201)
def create_reseller_customer(tenant_id: UUID, payload: ResellerCustomerCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    reseller = _reseller(db, tenant_id)
    count = db.scalar(select(func.count(ResellerCustomer.id)).where(ResellerCustomer.reseller_id == reseller.id)) or 0
    if int(count) >= reseller.max_customers:
        raise HTTPException(status_code=409, detail="Reseller customer limit reached")
    email = str(payload.admin_email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Admin email already has an account")
    slug = _slug(payload.company_slug or payload.company_name)
    if not slug:
        raise HTTPException(status_code=422, detail="Invalid company slug")
    if db.scalar(select(Tenant).where(Tenant.slug == slug)):
        slug = f"{slug[:68]}-{secrets.token_hex(4)}"
    ensure_default_plans(db)
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == payload.plan_code.lower(), BillingPlan.is_active.is_(True)))
    if plan is None:
        raise HTTPException(status_code=404, detail="Selected plan is unavailable")
    tenant = Tenant(name=payload.company_name.strip(), slug=slug)
    user = User(email=email, full_name=payload.admin_name.strip(), password_hash=hash_password(payload.admin_password), is_active=True, email_verified_at=datetime.now(timezone.utc))
    db.add_all([tenant, user])
    db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role=MembershipRole.tenant_admin))
    db.add(ResellerCustomer(reseller_id=reseller.id, customer_tenant_id=tenant.id))
    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.trialing, period_days=14)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="reseller.customer.create", resource_type="tenant", resource_id=str(tenant.id), metadata_json=json.dumps({"customer_tenant_id": str(tenant.id)})))
    db.commit()
    return {"tenant_id": str(tenant.id), "tenant_name": tenant.name, "admin_email": user.email, "plan": plan.code, "subscription_status": subscription.status.value}


@router.get("/tenants/{tenant_id}/reseller/customers")
def list_reseller_customers(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    reseller = _reseller(db, tenant_id)
    rows = db.execute(
        select(ResellerCustomer, Tenant)
        .join(Tenant, Tenant.id == ResellerCustomer.customer_tenant_id)
        .where(ResellerCustomer.reseller_id == reseller.id)
        .order_by(Tenant.name)
    ).all()
    return {"items": [{"id": str(rc.id), "tenant_id": str(t.id), "name": t.name, "slug": t.slug, "status": t.status.value, "created_at": rc.created_at.isoformat()} for rc, t in rows]}


@router.get("/tenants/{tenant_id}/registrar/status")
def registrar_status(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    return {"provider": "opensrs", "configured": opensrs_configured()}


@router.post("/tenants/{tenant_id}/registrar/lookup")
def registrar_lookup(tenant_id: UUID, payload: DomainLookup, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    try:
        return opensrs_lookup(payload.domain_name.strip().lower())
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/tenants/{tenant_id}/registrar/register", status_code=201)
def registrar_register(tenant_id: UUID, payload: DomainRegister, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    reseller = db.scalar(select(ResellerAccount).where(ResellerAccount.tenant_id == tenant_id))
    order = DomainOrder(
        tenant_id=tenant_id,
        reseller_id=reseller.id if reseller else None,
        domain_name=payload.domain_name.strip().lower(),
        operation="register",
        years=payload.years,
        provider="opensrs",
        status="processing",
        created_by_user_id=current.id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    try:
        result = opensrs_register(
            domain=order.domain_name,
            years=payload.years,
            registrant_username=payload.registrant_username,
            registrant_password=payload.registrant_password,
            nameserver_1=settings.nameserver_1,
            nameserver_2=settings.nameserver_2,
            owner_name=payload.owner_name,
            owner_email=str(payload.owner_email),
            owner_phone=payload.owner_phone,
            owner_address=payload.owner_address,
            owner_city=payload.owner_city,
            owner_country=payload.owner_country,
            owner_postal_code=payload.owner_postal_code,
        )
        order.status = "completed"
        order.provider_order_id = result.get("order_id") or result.get("id")
        order.response_json = json.dumps(result, sort_keys=True)
    except (ProviderConfigurationError, ProviderRequestError) as exc:
        order.status = "failed"
        order.response_json = json.dumps({"error": str(exc)})
        db.commit()
        raise HTTPException(status_code=503 if isinstance(exc, ProviderConfigurationError) else 502, detail=str(exc)) from exc
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="registrar.domain.register", resource_type="domain_order", resource_id=str(order.id), metadata_json=json.dumps({"domain": order.domain_name, "status": order.status})))
    db.commit()
    return {"id": str(order.id), "domain": order.domain_name, "status": order.status, "provider_order_id": order.provider_order_id}


@router.get("/tenants/{tenant_id}/registrar/orders")
def registrar_orders(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    rows = db.scalars(select(DomainOrder).where(DomainOrder.tenant_id == tenant_id).order_by(DomainOrder.created_at.desc()).limit(200)).all()
    return {"items": [{"id": str(x.id), "domain_name": x.domain_name, "operation": x.operation, "years": x.years, "provider": x.provider, "provider_order_id": x.provider_order_id, "status": x.status, "created_at": x.created_at.isoformat()} for x in rows]}


@router.post("/tenants/{tenant_id}/groupware/credentials", status_code=201)
def create_groupware_credential(tenant_id: UUID, payload: GroupwareCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.manage", db, current)
    mailbox = db.scalar(select(Mailbox).where(Mailbox.id == payload.mailbox_id, Mailbox.tenant_id == tenant_id, Mailbox.status == MailboxStatus.active))
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Active mailbox not found")
    row = db.scalar(select(GroupwareCredential).where(GroupwareCredential.mailbox_id == mailbox.id))
    hashed = hash_password(payload.password)
    if row is None:
        row = GroupwareCredential(tenant_id=tenant_id, mailbox_id=mailbox.id, username=mailbox.address, password_hash=hashed, active=True)
        db.add(row)
    else:
        row.password_hash = hashed
        row.active = True
    db.flush()
    _sync_groupware_auth(db)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="groupware.credential.upsert", resource_type="mailbox", resource_id=str(mailbox.id)))
    db.commit()
    base = settings.groupware_public_url.rstrip("/")
    return {"username": mailbox.address, "caldav_url": f"{base}/{mailbox.address}/", "carddav_url": f"{base}/{mailbox.address}/", "active": True}


@router.get("/tenants/{tenant_id}/groupware")
def groupware_status(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "mail.read", db, current)
    rows = db.execute(
        select(GroupwareCredential, Mailbox)
        .join(Mailbox, Mailbox.id == GroupwareCredential.mailbox_id)
        .where(GroupwareCredential.tenant_id == tenant_id)
        .order_by(Mailbox.address)
    ).all()
    return {"public_url": settings.groupware_public_url, "items": [{"id": str(g.id), "mailbox_id": str(m.id), "username": g.username, "active": g.active, "mailbox": m.address} for g, m in rows]}


@router.post("/platform/mail-nodes", status_code=201)
def create_mail_node(payload: MailNodeCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.scalar(select(MailNode).where(MailNode.name == payload.name))
    if row is None:
        row = MailNode(**payload.model_dump())
        db.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        row.status = "active"
    db.add(AuditLog(actor_user_id=current.id, action="mail_node.upsert", resource_type="mail_node", resource_id=str(row.id) if row.id else None))
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "name": row.name, "role": row.role, "region": row.region, "hostname": row.hostname, "public_ip": row.public_ip, "status": row.status, "weight": row.weight}


@router.get("/platform/mail-nodes")
def list_mail_nodes(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    rows = db.scalars(select(MailNode).order_by(MailNode.role, MailNode.region, MailNode.name)).all()
    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        fresh = bool(row.last_heartbeat_at and (now - row.last_heartbeat_at).total_seconds() <= settings.mail_node_stale_seconds)
        items.append({"id": str(row.id), "name": row.name, "role": row.role, "region": row.region, "hostname": row.hostname, "public_ip": row.public_ip, "status": row.status, "weight": row.weight, "last_heartbeat_at": row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None, "healthy": row.status == "active" and fresh})
    return {"items": items}


@router.post("/mail-nodes/{node_id}/heartbeat")
def mail_node_heartbeat(node_id: UUID, x_mail_node_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not settings.mail_node_token or not secrets.compare_digest(x_mail_node_token or "", settings.mail_node_token):
        raise HTTPException(status_code=401, detail="Invalid mail node token")
    row = db.get(MailNode, node_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mail node not found")
    row.last_heartbeat_at = datetime.now(timezone.utc)
    row.status = "active"
    db.commit()
    return {"healthy": True, "node_id": str(row.id)}
