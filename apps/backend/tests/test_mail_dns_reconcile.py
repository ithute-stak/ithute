from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.models import Mailbox, MailboxStatus, SubscriptionStatus, Tenant, TenantSubscription
from app.models.deliverability import DkimKey
from app.models.domains import Domain, DomainDnsMode, DomainStatus
from app.services import mail_dns_reconcile
from app.services.billing import ensure_default_plans
from app.services.system_mailboxes import (
    SYSTEM_DOMAIN,
    SYSTEM_MAILBOXES,
    SYSTEM_TENANT_SLUG,
    ensure_system_mailboxes,
)


class FakePowerDNS:
    def __init__(self):
        self.zone = {
            "rrsets": [
                {
                    "name": "example.com.",
                    "type": "TXT",
                    "records": [
                        {"content": '"google-site-verification=keep-me"'},
                        {"content": '"v=spf1 ~all"'},
                    ],
                }
            ]
        }
        self.replacements = []
        self.rectified = False

    def get_zone(self, name):
        return self.zone

    def create_zone_with_nameservers(self, name, nameservers):
        return self.zone

    def reconcile_authority(self, name):
        return self.zone

    def replace_rrset(self, zone, name, rtype, ttl, contents):
        self.replacements.append((zone, name, rtype, ttl, list(contents)))

    def rectify_zone(self, name):
        self.rectified = True


def test_reconcile_mail_dns_generates_dkim_and_preserves_unrelated_txt(db, tenant_admin, monkeypatch):
    user, tenant, _membership = tenant_admin
    domain = Domain(
        tenant_id=tenant.id,
        ascii_name="example.com",
        unicode_name="example.com",
        status=DomainStatus.verified,
        dns_mode=DomainDnsMode.platform,
        mail_enabled=True,
        verification_token_hash="a" * 64,
        verification_token_hint="12345678",
        verification_record_name="_mailbox-dns-verification.example.com",
        ownership_verified_at=datetime.now(timezone.utc),
        created_by_user_id=user.id,
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)

    fake = FakePowerDNS()
    monkeypatch.setattr(mail_dns_reconcile.settings, "mail_hostname", "mail.ithute.co.ls")
    monkeypatch.setattr(mail_dns_reconcile.settings, "powerdns_default_ttl", 3600)
    monkeypatch.setattr(mail_dns_reconcile, "sync_active_dkim_keys", lambda _db: 1)

    try:
        first = mail_dns_reconcile.reconcile_mail_dns(db, domain, user.id, client=fake)
        assert first.selector == "s1"
        assert first.dkim_created is True
        assert first.rspamd_synced_domains == 1
        assert fake.rectified is True

        replacements = {(name, rtype): contents for _zone, name, rtype, _ttl, contents in fake.replacements}
        assert replacements[("example.com", "MX")] == ["10 mail.ithute.co.ls."]
        assert '"google-site-verification=keep-me"' in replacements[("example.com", "TXT")]
        assert '"v=spf1 mx -all"' in replacements[("example.com", "TXT")]
        assert '"v=spf1 ~all"' not in replacements[("example.com", "TXT")]
        assert replacements[("_dmarc.example.com", "TXT")] == ['"v=DMARC1; p=quarantine; adkim=s; aspf=s; pct=100"']
        dkim_values = replacements[("s1._domainkey.example.com", "TXT")]
        assert len(dkim_values) == 1
        assert dkim_values[0].startswith('"v=DKIM1; k=rsa; p=')

        first_key_id = db.scalar(select(DkimKey.id).where(DkimKey.domain_id == domain.id))
        second = mail_dns_reconcile.reconcile_mail_dns(db, domain, user.id, client=FakePowerDNS())
        assert second.dkim_created is False
        assert db.scalar(select(func.count()).select_from(DkimKey).where(DkimKey.domain_id == domain.id)) == 1
        assert db.scalar(select(DkimKey.id).where(DkimKey.domain_id == domain.id)) == first_key_id
    finally:
        db.execute(delete(DkimKey).where(DkimKey.domain_id == domain.id))
        db.execute(delete(Domain).where(Domain.id == domain.id))
        db.commit()


def test_builtin_ithute_mailboxes_are_active_and_bootstrap_is_idempotent(db, platform_owner):
    tenant = db.scalar(select(Tenant).where(Tenant.slug == SYSTEM_TENANT_SLUG))
    if tenant is not None:
        db.execute(delete(Mailbox).where(Mailbox.tenant_id == tenant.id))
        db.execute(delete(Domain).where(Domain.tenant_id == tenant.id))
        db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
        db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()

    ensure_default_plans(db)
    try:
        first = ensure_system_mailboxes(db, platform_owner)
        expected = tuple(f"{local}@{SYSTEM_DOMAIN}" for local, _ in SYSTEM_MAILBOXES)
        assert first.addresses == expected
        assert first.created_addresses == expected

        tenant = db.scalar(select(Tenant).where(Tenant.slug == SYSTEM_TENANT_SLUG))
        assert tenant is not None
        domain = db.scalar(select(Domain).where(Domain.ascii_name == SYSTEM_DOMAIN))
        assert domain is not None
        assert domain.tenant_id == tenant.id
        assert domain.mail_enabled is True
        assert domain.status == DomainStatus.verified
        assert domain.dns_mode == DomainDnsMode.platform
        assert domain.ownership_verified_at is not None

        mailboxes = db.scalars(select(Mailbox).where(Mailbox.tenant_id == tenant.id).order_by(Mailbox.address)).all()
        assert {item.address for item in mailboxes} == set(expected)
        assert all(item.status == MailboxStatus.active for item in mailboxes)
        password_hashes = {item.address: item.password_hash for item in mailboxes}

        subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
        assert subscription is not None
        assert subscription.status == SubscriptionStatus.active
        assert subscription.provider == "system-internal"

        second = ensure_system_mailboxes(db, platform_owner)
        assert second.created_addresses == ()
        db.expire_all()
        mailboxes_after = db.scalars(select(Mailbox).where(Mailbox.tenant_id == tenant.id)).all()
        assert {item.address: item.password_hash for item in mailboxes_after} == password_hashes
    finally:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == SYSTEM_TENANT_SLUG))
        if tenant is not None:
            db.execute(delete(Mailbox).where(Mailbox.tenant_id == tenant.id))
            db.execute(delete(Domain).where(Domain.tenant_id == tenant.id))
            db.execute(delete(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
            db.execute(delete(Tenant).where(Tenant.id == tenant.id))
            db.commit()
