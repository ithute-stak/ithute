from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Domain,
    DomainDnsMode,
    DomainStatus,
    Mailbox,
    MailboxStatus,
    MembershipRole,
    MembershipStatus,
    Tenant,
    TenantMembership,
    User,
)
from app.services.mailboxes import hash_mailbox_password

ADDRESS = "phase6@phase6.test"
PASSWORD = "Phase6Strong!Pass"


def main() -> None:
    db = SessionLocal()
    try:
        membership = db.scalar(select(TenantMembership).order_by(TenantMembership.created_at))
        if membership is None:
            actor = db.scalar(select(User).where(User.is_platform_owner.is_(True)).order_by(User.created_at))
            if actor is None:
                raise RuntimeError("bootstrap platform owner is required before Phase 6 fixture seeding")
            tenant = db.scalar(select(Tenant).where(Tenant.slug == "phase6-fixture"))
            if tenant is None:
                tenant = Tenant(name="Phase 6 Fixture", slug="phase6-fixture")
                db.add(tenant)
                db.flush()
            membership = TenantMembership(
                tenant_id=tenant.id,
                user_id=actor.id,
                role=MembershipRole.tenant_admin,
                status=MembershipStatus.active,
            )
            db.add(membership)
            db.flush()
        else:
            actor = db.get(User, membership.user_id)
            if actor is None:
                raise RuntimeError("fixture actor user not found")

        domain = db.scalar(select(Domain).where(Domain.ascii_name == "phase6.test"))
        if domain is None:
            domain = Domain(
                tenant_id=membership.tenant_id,
                ascii_name="phase6.test",
                unicode_name="phase6.test",
                status=DomainStatus.verified,
                dns_mode=DomainDnsMode.external,
                mail_enabled=True,
                verification_token_hash="0" * 64,
                verification_token_hint="fixture",
                verification_record_name="_mailbox-dns-verification.phase6.test",
                created_by_user_id=actor.id,
            )
            db.add(domain)
            db.flush()
        else:
            domain.status = DomainStatus.verified
            domain.mail_enabled = True

        mailbox = db.scalar(select(Mailbox).where(Mailbox.address == ADDRESS))
        if mailbox is None:
            mailbox = Mailbox(
                tenant_id=domain.tenant_id,
                domain_id=domain.id,
                local_part="phase6",
                address=ADDRESS,
                password_hash=hash_mailbox_password(PASSWORD),
                quota_bytes=1024**3,
                status=MailboxStatus.active,
                created_by_user_id=actor.id,
            )
            db.add(mailbox)
        else:
            mailbox.status = MailboxStatus.active
            mailbox.password_hash = hash_mailbox_password(PASSWORD)
        db.commit()
        print("Phase 6 database-backed fixture ready.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
