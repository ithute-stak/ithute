import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_membership, require_tenant_permission
from app.core.security import hash_password
from app.db.session import get_db
from app.models import (
    AuditLog, BillingInvoice, BillingPlan, CustomerProfile, Domain, InvoiceStatus, Mailbox,
    MembershipRole, Notification, ServiceIncident, ServiceIncidentImpact, ServiceIncidentStatus,
    SubscriptionStatus, SupportTicket, SupportTicketMessage, SupportTicketPriority,
    SupportTicketStatus, Tenant, TenantMembership, TenantSubscription, User,
)
from app.services.billing import assign_subscription, ensure_default_plans, generate_invoice

router = APIRouter(tags=["business"])


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:80]


def _ticket_number() -> str:
    return f"MD-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"


def _incident_out(row: ServiceIncident) -> dict:
    return {"id": str(row.id), "title": row.title, "summary": row.summary, "status": row.status.value, "impact": row.impact.value, "started_at": row.started_at.isoformat() if row.started_at else None, "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None}


def _ticket_out(row: SupportTicket) -> dict:
    return {"id": str(row.id), "ticket_number": row.ticket_number, "tenant_id": str(row.tenant_id), "created_by_user_id": str(row.created_by_user_id), "assigned_to_user_id": str(row.assigned_to_user_id) if row.assigned_to_user_id else None, "subject": row.subject, "category": row.category, "description": row.description, "status": row.status.value, "priority": row.priority.value, "created_at": row.created_at.isoformat() if row.created_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None, "closed_at": row.closed_at.isoformat() if row.closed_at else None}


def _profile_out(row: CustomerProfile) -> dict:
    return {"tenant_id": str(row.tenant_id), "billing_email": row.billing_email, "phone": row.phone, "address_line1": row.address_line1, "address_line2": row.address_line2, "city": row.city, "country": row.country, "company_registration_number": row.company_registration_number, "tax_number": row.tax_number}


class PublicSignup(BaseModel):
    company_name: str = Field(min_length=2, max_length=150)
    company_slug: str | None = Field(default=None, max_length=80)
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    plan_code: str = Field(default="business", min_length=2, max_length=50)
    phone: str | None = Field(default=None, max_length=60)
    terms_accepted: bool

    @field_validator("company_slug")
    @classmethod
    def validate_slug(cls, value: str | None):
        if value is None:
            return value
        normalized = _slug(value)
        if not normalized:
            raise ValueError("company_slug must contain letters or numbers")
        return normalized


class ProfileUpdate(BaseModel):
    billing_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=60)
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    country: str = Field(default="Lesotho", min_length=2, max_length=120)
    company_registration_number: str | None = Field(default=None, max_length=120)
    tax_number: str | None = Field(default=None, max_length=120)


class TicketCreate(BaseModel):
    subject: str = Field(min_length=4, max_length=200)
    category: str = Field(default="general", min_length=2, max_length=80)
    description: str = Field(min_length=10, max_length=20_000)
    priority: SupportTicketPriority = SupportTicketPriority.normal


class TicketMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)


class TicketUpdate(BaseModel):
    status: SupportTicketStatus | None = None
    priority: SupportTicketPriority | None = None
    assigned_to_user_id: UUID | None = None


class IncidentCreate(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    summary: str = Field(min_length=10, max_length=20_000)
    impact: ServiceIncidentImpact = ServiceIncidentImpact.minor


class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=4, max_length=180)
    summary: str | None = Field(default=None, min_length=10, max_length=20_000)
    status: ServiceIncidentStatus | None = None
    impact: ServiceIncidentImpact | None = None


class ManualPayment(BaseModel):
    reference: str = Field(min_length=2, max_length=160)


@router.get("/public/pricing")
def public_pricing(db: Session = Depends(get_db)):
    ensure_default_plans(db)
    plans = db.scalars(select(BillingPlan).where(BillingPlan.is_active.is_(True)).order_by(BillingPlan.monthly_price_minor)).all()
    return {"currency": "LSL", "items": [{"code": p.code, "name": p.name, "monthly_price_minor": p.monthly_price_minor, "included_mailboxes": p.included_mailboxes, "included_domains": p.included_domains, "included_storage_mb": p.included_storage_mb, "max_api_keys": p.max_api_keys} for p in plans]}


@router.post("/public/signup", status_code=201)
def public_signup(payload: PublicSignup, db: Session = Depends(get_db)):
    if not payload.terms_accepted:
        raise HTTPException(status_code=422, detail="Terms of Service and Acceptable Use Policy must be accepted")
    email = str(payload.email).strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    slug = payload.company_slug or _slug(payload.company_name)
    if not slug:
        raise HTTPException(status_code=422, detail="Unable to create a company slug")
    if db.scalar(select(Tenant).where(Tenant.slug == slug)):
        slug = f"{slug[:68]}-{uuid4().hex[:8]}"
    ensure_default_plans(db)
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == payload.plan_code.strip().lower(), BillingPlan.is_active.is_(True)))
    if plan is None:
        raise HTTPException(status_code=404, detail="Selected plan is unavailable")
    tenant = Tenant(name=payload.company_name.strip(), slug=slug)
    user = User(email=email, password_hash=hash_password(payload.password), full_name=payload.full_name.strip(), is_active=True)
    db.add_all([tenant, user]); db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role=MembershipRole.tenant_admin))
    db.add(CustomerProfile(tenant_id=tenant.id, billing_email=email, phone=payload.phone, country="Lesotho")); db.flush()
    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.trialing, period_days=14)
    db.add(Notification(tenant_id=tenant.id, user_id=user.id, category="onboarding", severity="success", title="Welcome to Mailbox DNS", message="Your 14-day trial is active. Add and verify your first domain to start provisioning mail and DNS.", action_url="/onboarding"))
    db.add(AuditLog(tenant_id=tenant.id, actor_user_id=user.id, action="customer.signup", resource_type="tenant", resource_id=str(tenant.id)))
    db.commit()
    return {"created": True, "tenant": {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug}, "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name}, "subscription": {"plan": plan.code, "status": subscription.status.value, "trial_ends_at": subscription.current_period_end.isoformat()}, "login_url": "/login"}


@router.get("/public/status")
def public_status(db: Session = Depends(get_db)):
    incidents = db.scalars(select(ServiceIncident).order_by(ServiceIncident.started_at.desc()).limit(20)).all()
    active = [x for x in incidents if x.status != ServiceIncidentStatus.resolved]
    overall = "major_outage" if any(x.impact == ServiceIncidentImpact.critical for x in active) else "degraded" if any(x.impact == ServiceIncidentImpact.major for x in active) else "minor_issue" if active else "operational"
    return {"status": overall, "incidents": [_incident_out(x) for x in incidents]}


@router.get("/tenants/{tenant_id}/customer-profile")
def get_customer_profile(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_platform_owner: require_tenant_membership(tenant_id, db, current)
    row = db.scalar(select(CustomerProfile).where(CustomerProfile.tenant_id == tenant_id))
    if row is None:
        row = CustomerProfile(tenant_id=tenant_id, country="Lesotho"); db.add(row); db.commit(); db.refresh(row)
    return _profile_out(row)


@router.patch("/tenants/{tenant_id}/customer-profile")
def update_customer_profile(tenant_id: UUID, payload: ProfileUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    row = db.scalar(select(CustomerProfile).where(CustomerProfile.tenant_id == tenant_id)) or CustomerProfile(tenant_id=tenant_id)
    db.add(row)
    for key, value in payload.model_dump().items(): setattr(row, key, str(value) if key == "billing_email" and value is not None else value)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="customer.profile.update", resource_type="customer_profile", resource_id=str(tenant_id)))
    db.commit(); db.refresh(row)
    return _profile_out(row)


@router.get("/tenants/{tenant_id}/notifications")
def list_notifications(tenant_id: UUID, unread_only: bool = Query(default=False), limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_platform_owner: require_tenant_membership(tenant_id, db, current)
    query = select(Notification).where(Notification.tenant_id == tenant_id, or_(Notification.user_id.is_(None), Notification.user_id == current.id))
    if unread_only: query = query.where(Notification.read_at.is_(None))
    rows = db.scalars(query.order_by(Notification.created_at.desc()).limit(limit)).all()
    return {"items": [{"id": str(x.id), "category": x.category, "severity": x.severity, "title": x.title, "message": x.message, "action_url": x.action_url, "read_at": x.read_at.isoformat() if x.read_at else None, "created_at": x.created_at.isoformat()} for x in rows]}


@router.post("/tenants/{tenant_id}/notifications/{notification_id}/read")
def read_notification(tenant_id: UUID, notification_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_platform_owner: require_tenant_membership(tenant_id, db, current)
    row = db.get(Notification, notification_id)
    if row is None or row.tenant_id != tenant_id or (row.user_id is not None and row.user_id != current.id and not current.is_platform_owner): raise HTTPException(status_code=404, detail="Notification not found")
    row.read_at = datetime.now(timezone.utc); db.commit(); return {"read": True}


@router.post("/tenants/{tenant_id}/notifications/read-all")
def read_all_notifications(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_platform_owner: require_tenant_membership(tenant_id, db, current)
    rows = db.scalars(select(Notification).where(Notification.tenant_id == tenant_id, or_(Notification.user_id.is_(None), Notification.user_id == current.id), Notification.read_at.is_(None))).all()
    now = datetime.now(timezone.utc)
    for row in rows: row.read_at = now
    db.commit(); return {"updated": len(rows)}


@router.post("/tenants/{tenant_id}/support/tickets", status_code=201)
def create_support_ticket(tenant_id: UUID, payload: TicketCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_platform_owner: require_tenant_membership(tenant_id, db, current)
    ticket = SupportTicket(ticket_number=_ticket_number(), tenant_id=tenant_id, created_by_user_id=current.id, subject=payload.subject.strip(), category=payload.category.strip().lower(), description=payload.description.strip(), priority=payload.priority)
    db.add(ticket); db.flush()
    db.add(Notification(tenant_id=tenant_id, user_id=current.id, category="support", severity="info", title=f"Support ticket {ticket.ticket_number} opened", message=ticket.subject, action_url="/support"))
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="support.ticket.create", resource_type="support_ticket", resource_id=str(ticket.id)))
    db.commit(); db.refresh(ticket); return _ticket_out(ticket)


@router.get("/tenants/{tenant_id}/support/tickets")
def list_tenant_tickets(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_platform_owner: require_tenant_membership(tenant_id, db, current)
    rows = db.scalars(select(SupportTicket).where(SupportTicket.tenant_id == tenant_id).order_by(SupportTicket.created_at.desc()).limit(200)).all()
    return {"items": [_ticket_out(x) for x in rows]}


@router.get("/tenants/{tenant_id}/support/tickets/{ticket_id}")
def get_ticket(tenant_id: UUID, ticket_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_platform_owner: require_tenant_membership(tenant_id, db, current)
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None or ticket.tenant_id != tenant_id: raise HTTPException(status_code=404, detail="Support ticket not found")
    query = select(SupportTicketMessage).where(SupportTicketMessage.ticket_id == ticket.id)
    if not current.is_platform_owner: query = query.where(SupportTicketMessage.is_internal.is_(False))
    messages = db.scalars(query.order_by(SupportTicketMessage.created_at.asc())).all()
    return {**_ticket_out(ticket), "messages": [{"id": str(x.id), "author_user_id": str(x.author_user_id) if x.author_user_id else None, "author_role": x.author_role, "body": x.body, "is_internal": x.is_internal, "created_at": x.created_at.isoformat()} for x in messages]}


@router.post("/tenants/{tenant_id}/support/tickets/{ticket_id}/messages", status_code=201)
def add_ticket_message(tenant_id: UUID, ticket_id: UUID, payload: TicketMessageCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_platform_owner: require_tenant_membership(tenant_id, db, current)
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None or ticket.tenant_id != tenant_id: raise HTTPException(status_code=404, detail="Support ticket not found")
    message = SupportTicketMessage(ticket_id=ticket.id, author_user_id=current.id, author_role="platform" if current.is_platform_owner else "customer", body=payload.body.strip(), is_internal=False)
    db.add(message)
    if not current.is_platform_owner: ticket.status = SupportTicketStatus.open
    ticket.updated_at = datetime.now(timezone.utc); db.commit(); db.refresh(message)
    return {"id": str(message.id), "created_at": message.created_at.isoformat()}


@router.get("/support/tickets")
def platform_support_queue(status: SupportTicketStatus | None = None, priority: SupportTicketPriority | None = None, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    query = select(SupportTicket)
    if status is not None: query = query.where(SupportTicket.status == status)
    if priority is not None: query = query.where(SupportTicket.priority == priority)
    rows = db.scalars(query.order_by(SupportTicket.created_at.desc()).limit(500)).all()
    return {"items": [_ticket_out(x) for x in rows]}


@router.patch("/support/tickets/{ticket_id}")
def update_support_ticket(ticket_id: UUID, payload: TicketUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None: raise HTTPException(status_code=404, detail="Support ticket not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(ticket, key, value)
    if ticket.status in {SupportTicketStatus.resolved, SupportTicketStatus.closed}: ticket.closed_at = ticket.closed_at or datetime.now(timezone.utc)
    elif payload.status is not None: ticket.closed_at = None
    db.add(AuditLog(tenant_id=ticket.tenant_id, actor_user_id=current.id, action="support.ticket.update", resource_type="support_ticket", resource_id=str(ticket.id)))
    db.commit(); db.refresh(ticket); return _ticket_out(ticket)


@router.post("/service-incidents", status_code=201)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = ServiceIncident(title=payload.title.strip(), summary=payload.summary.strip(), impact=payload.impact, created_by_user_id=current.id)
    db.add(row); db.commit(); db.refresh(row); return _incident_out(row)


@router.patch("/service-incidents/{incident_id}")
def update_incident(incident_id: UUID, payload: IncidentUpdate, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.get(ServiceIncident, incident_id)
    if row is None: raise HTTPException(status_code=404, detail="Incident not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value)
    if row.status == ServiceIncidentStatus.resolved: row.resolved_at = row.resolved_at or datetime.now(timezone.utc)
    elif payload.status is not None: row.resolved_at = None
    db.commit(); db.refresh(row); return _incident_out(row)


@router.get("/platform/business/summary")
def platform_business_summary(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    tenant_count = db.scalar(select(func.count(Tenant.id))) or 0
    user_count = db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
    mailbox_count = db.scalar(select(func.count(Mailbox.id))) or 0
    domain_count = db.scalar(select(func.count(Domain.id))) or 0
    active_subscriptions = db.scalar(select(func.count(TenantSubscription.id)).where(TenantSubscription.status.in_([SubscriptionStatus.active, SubscriptionStatus.trialing]))) or 0
    mrr_minor = db.scalar(select(func.coalesce(func.sum(BillingPlan.monthly_price_minor), 0)).select_from(TenantSubscription).join(BillingPlan, BillingPlan.id == TenantSubscription.plan_id).where(TenantSubscription.status == SubscriptionStatus.active)) or 0
    open_invoice_minor = db.scalar(select(func.coalesce(func.sum(BillingInvoice.total_minor), 0)).where(BillingInvoice.status == InvoiceStatus.open)) or 0
    open_tickets = db.scalar(select(func.count(SupportTicket.id)).where(SupportTicket.status.in_([SupportTicketStatus.open, SupportTicketStatus.in_progress, SupportTicketStatus.pending_customer]))) or 0
    urgent_tickets = db.scalar(select(func.count(SupportTicket.id)).where(SupportTicket.priority == SupportTicketPriority.urgent, SupportTicket.status.notin_([SupportTicketStatus.resolved, SupportTicketStatus.closed]))) or 0
    return {"currency": "LSL", "tenants": int(tenant_count), "active_users": int(user_count), "mailboxes": int(mailbox_count), "domains": int(domain_count), "active_or_trial_subscriptions": int(active_subscriptions), "mrr_minor": int(mrr_minor), "open_invoice_minor": int(open_invoice_minor), "open_support_tickets": int(open_tickets), "urgent_support_tickets": int(urgent_tickets)}


@router.post("/billing/invoices/{invoice_id}/mark-paid")
def mark_invoice_paid_manual(invoice_id: UUID, payload: ManualPayment, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    invoice = db.get(BillingInvoice, invoice_id)
    if invoice is None: raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = InvoiceStatus.paid; invoice.paid_at = datetime.now(timezone.utc)
    if invoice.subscription_id:
        subscription = db.get(TenantSubscription, invoice.subscription_id)
        if subscription is not None:
            subscription.status = SubscriptionStatus.active; subscription.past_due_since = None; subscription.grace_ends_at = None
    db.add(AuditLog(tenant_id=invoice.tenant_id, actor_user_id=current.id, action="billing.invoice.manual_payment", resource_type="billing_invoice", resource_id=str(invoice.id), metadata_json='{"payment_reference":"manual"}'))
    db.commit(); return {"paid": True, "invoice_id": str(invoice.id), "reference": payload.reference}


@router.post("/tenants/{tenant_id}/billing/manual-invoice", status_code=201)
def customer_request_invoice(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    try: invoice = generate_invoice(db, tenant_id)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number, "currency": invoice.currency, "total_minor": invoice.total_minor, "status": invoice.status.value, "due_at": invoice.due_at.isoformat() if invoice.due_at else None, "payment_method": "manual", "payment_reference": invoice.invoice_number}
