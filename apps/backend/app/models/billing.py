import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SubscriptionStatus(str, enum.Enum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    paid = "paid"
    void = "void"
    uncollectible = "uncollectible"


class BillingPlan(Base):
    __tablename__ = "billing_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="LSL", nullable=False)
    monthly_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    included_mailboxes: Mapped[int] = mapped_column(Integer, nullable=False)
    included_domains: Mapped[int] = mapped_column(Integer, nullable=False)
    included_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    max_api_keys: Mapped[int] = mapped_column(Integer, nullable=False)

    # Shared application-hosting entitlements. Hosting storage is deliberately
    # separate from mailbox storage: a website filling its disk allocation must
    # never consume or redefine the organization's mail quota.
    included_hosted_projects: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    hosting_storage_mb: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    hosting_memory_mb_per_project: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    hosting_cpu_millicores_per_project: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    hosting_pids_per_project: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # Commercial deliverables are stored on the package as first-class data so
    # the public catalogue and contracts describe exactly what the customer buys.
    product_category: Mapped[str] = mapped_column(String(80), default="Website & Hosting", server_default="Website & Hosting", nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    website_pages: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    includes_website_design: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    includes_logo_design: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    includes_brand_guide: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    includes_company_profile: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    includes_letterhead: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    includes_page_headers_footers: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    includes_business_templates: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    included_revisions: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    content_updates_per_month: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    support_level: Mapped[str] = mapped_column(String(40), default="standard", server_default="standard", nullable=False)
    minimum_term_months: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    price_from: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TenantSubscription(Base):
    __tablename__ = "tenant_subscriptions"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_subscription_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("billing_plans.id"), index=True, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus), default=SubscriptionStatus.trialing, nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    provider_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    past_due_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UsageSnapshot(Base):
    __tablename__ = "usage_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    mailboxes: Mapped[int] = mapped_column(Integer, nullable=False)
    domains: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenant_subscriptions.id", ondelete="SET NULL"), index=True, nullable=True)
    usage_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usage_snapshots.id", ondelete="SET NULL"), index=True, nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.draft, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_invoice_id: Mapped[str | None] = mapped_column(String(160), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingPaymentEvent(Base):
    __tablename__ = "billing_payment_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_billing_payment_event_provider_event"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    event_id: Mapped[str] = mapped_column(String(180), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), index=True, nullable=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("billing_invoices.id", ondelete="SET NULL"), index=True, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
