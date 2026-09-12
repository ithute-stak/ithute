from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BillingPlan,
    Domain,
    DomainDnsMode,
    DomainStatus,
    Mailbox,
    MailboxStatus,
    SubscriptionStatus,
    Tenant,
    TenantStatus,
    TenantSubscription,
    User,
)
from app.services.mailboxes import hash_mailbox_password

SYSTEM_TENANT_NAME = "ithute.co.ls"
SYSTEM_TENANT_SLUG = "ithute-system"
SYSTEM_DOMAIN = "ithute.co.ls"
SYSTEM_MAILBOXES: tuple[tuple[str, str], ...] = (
    ("info", "!thute Information"),
    ("supperadmin", "!thute Super Admin"),
    ("thekoetlisi", "Thekoetlisi"),
)


@dataclass(frozen=True)
class SystemMailboxBootstrapResult:
    tenant_id: str
    domain_id: str
    addresses: tuple[str, ...]
    created_addresses: tuple[str, ...]


def _system_verification_hash() -> str:
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()


def _ensure_system_tenant(db: Session) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == SYSTEM_TENANT_SLUG))
    if tenant is None:
        tenant = Tenant(name=SYSTEM_TENANT_NAME, slug=SYSTEM_TENANT_SLUG, status=TenantStatus.active)
        db.add(tenant)
        db.flush()
    else:
        tenant.name = SYSTEM_TENANT_NAME
        tenant.status = TenantStatus.active
    return tenant


def _ensure_system_subscription(db: Session, tenant: Tenant) -> None:
    """Give the platform-owned tenant capacity for dashboard-created mailboxes.

    This is an internal/manual subscription only.  It exists so normal mailbox
    entitlement checks keep applying to customer tenants while the platform
    owner can add more @ithute.co.ls mailboxes from the existing dashboard.
    """

    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "enterprise"))
    if plan is None:
        raise RuntimeError("Enterprise billing plan must exist before system mailbox bootstrap")

    subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
    now = datetime.now(timezone.utc)
    if subscription is None:
        subscription = TenantSubscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status=SubscriptionStatus.active,
            current_period_start=now,
            current_period_end=now + timedelta(days=36500),
            provider="system-internal",
        )
        db.add(subscription)
    else:
        subscription.plan_id = plan.id
        subscription.status = SubscriptionStatus.active
        subscription.provider = "system-internal"
        subscription.cancel_at_period_end = False
        subscription.past_due_since = None
        subscription.grace_ends_at = None
        if subscription.current_period_end <= now + timedelta(days=3650):
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=36500)


def _ensure_system_domain(db: Session, tenant: Tenant, owner: User) -> Domain:
    domain = db.scalar(select(Domain).where(Domain.ascii_name == SYSTEM_DOMAIN))
    now = datetime.now(timezone.utc)
    if domain is not None and domain.tenant_id != tenant.id:
        raise RuntimeError(f"{SYSTEM_DOMAIN} is already assigned to a non-system tenant")

    if domain is None:
        domain = Domain(
            tenant_id=tenant.id,
            ascii_name=SYSTEM_DOMAIN,
            unicode_name=SYSTEM_DOMAIN,
            status=DomainStatus.verified,
            dns_mode=DomainDnsMode.platform,
            mail_enabled=True,
            notes="Platform-owned !thute system mail domain",
            verification_token_hash=_system_verification_hash(),
            verification_token_hint="system-owned",
            verification_record_name=f"_mdns-verify.{SYSTEM_DOMAIN}",
            ownership_verified_at=now,
            created_by_user_id=owner.id,
        )
        db.add(domain)
        db.flush()
    else:
        domain.status = DomainStatus.verified
        domain.dns_mode = DomainDnsMode.platform
        domain.mail_enabled = True
        domain.ownership_verified_at = domain.ownership_verified_at or now
        domain.notes = domain.notes or "Platform-owned !thute system mail domain"
    return domain


def _ensure_mailbox(db: Session, tenant: Tenant, domain: Domain, owner: User, local_part: str, display_name: str) -> tuple[Mailbox, bool]:
    address = f"{local_part}@{SYSTEM_DOMAIN}"
    mailbox = db.scalar(select(Mailbox).where(Mailbox.address == address))
    if mailbox is not None and mailbox.tenant_id != tenant.id:
        raise RuntimeError(f"{address} is already assigned to a non-system tenant")

    if mailbox is None:
        # The bootstrap credential exists only long enough to create a valid
        # Dovecot password hash.  It is never logged or stored in plaintext.
        # A platform owner can set the usable mailbox password from Dashboard
        # -> Mailboxes before the first interactive Webmail login.
        bootstrap_password = secrets.token_urlsafe(32) + "!Aa1"
        mailbox = Mailbox(
            tenant_id=tenant.id,
            domain_id=domain.id,
            local_part=local_part,
            address=address,
            display_name=display_name,
            password_hash=hash_mailbox_password(bootstrap_password),
            quota_bytes=5 * 1024**3,
            status=MailboxStatus.active,
            created_by_user_id=owner.id,
        )
        db.add(mailbox)
        db.flush()
        return mailbox, True

    mailbox.domain_id = domain.id
    mailbox.local_part = local_part
    mailbox.status = MailboxStatus.active
    mailbox.display_name = mailbox.display_name or display_name
    return mailbox, False


def ensure_system_mailboxes(db: Session, owner: User) -> SystemMailboxBootstrapResult:
    if not owner.is_platform_owner:
        raise RuntimeError("System mailboxes can only be provisioned by the platform owner")

    tenant = _ensure_system_tenant(db)
    _ensure_system_subscription(db, tenant)
    domain = _ensure_system_domain(db, tenant, owner)

    addresses: list[str] = []
    created: list[str] = []
    for local_part, display_name in SYSTEM_MAILBOXES:
        mailbox, was_created = _ensure_mailbox(db, tenant, domain, owner, local_part, display_name)
        addresses.append(mailbox.address)
        if was_created:
            created.append(mailbox.address)

    db.commit()
    return SystemMailboxBootstrapResult(
        tenant_id=str(tenant.id),
        domain_id=str(domain.id),
        addresses=tuple(addresses),
        created_addresses=tuple(created),
    )
