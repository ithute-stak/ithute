from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deliverability import DkimKey
from app.models.domains import Domain, DomainDnsMode, DomainStatus
from app.services.deliverability import generate_dkim_material, recommended_records
from app.services.dkim_sync import sync_active_dkim_keys
from app.services.powerdns import PowerDNSClient, PowerDNSError, validate_record


class MailDNSReconcileError(RuntimeError):
    pass


@dataclass(frozen=True)
class MailDNSReconcileResult:
    domain: str
    selector: str
    dkim_created: bool
    rspamd_synced_domains: int
    records: list[dict]


def _active_key(db: Session, domain: Domain) -> DkimKey | None:
    return db.scalar(
        select(DkimKey)
        .where(DkimKey.domain_id == domain.id, DkimKey.active.is_(True))
        .order_by(DkimKey.created_at.desc())
    )


def _next_selector(db: Session, domain: Domain) -> str:
    used = set(
        db.scalars(select(DkimKey.selector).where(DkimKey.domain_id == domain.id)).all()
    )
    for number in range(1, 100):
        candidate = f"s{number}"
        if candidate not in used:
            return candidate
    raise MailDNSReconcileError("No free automatic DKIM selector is available")


def _ensure_active_key(db: Session, domain: Domain, actor_user_id: UUID) -> tuple[DkimKey, bool]:
    key = _active_key(db, domain)
    if key:
        return key, False

    selector = _next_selector(db, domain)
    encrypted, public = generate_dkim_material()
    key = DkimKey(
        tenant_id=domain.tenant_id,
        domain_id=domain.id,
        selector=selector,
        public_key_b64=public,
        private_key_encrypted=encrypted,
        active=True,
        created_by_user_id=actor_user_id,
    )
    db.add(key)
    db.flush()

    # Persist the signing identity before external DNS/Rspamd side effects. If a
    # later operation fails, a retry reuses this same key instead of publishing
    # a public key whose matching private key was rolled back.
    db.commit()
    db.refresh(key)
    db.refresh(domain)
    return key, True


def _strip_txt_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _existing_rrset_contents(zone: dict, name: str, rtype: str) -> list[str]:
    expected_name = name.rstrip(".").lower()
    expected_type = rtype.upper()
    rrsets = zone.get("rrsets") if isinstance(zone, dict) else None
    for rrset in rrsets if isinstance(rrsets, list) else []:
        if not isinstance(rrset, dict):
            continue
        if str(rrset.get("name", "")).rstrip(".").lower() != expected_name:
            continue
        if str(rrset.get("type", "")).upper() != expected_type:
            continue
        records = rrset.get("records") if isinstance(rrset.get("records"), list) else []
        return [
            str(record.get("content", "")).strip()
            for record in records
            if isinstance(record, dict) and str(record.get("content", "")).strip()
        ]
    return []


def _zone_or_create(client: PowerDNSClient, domain_name: str) -> dict:
    try:
        zone = client.get_zone(domain_name)
    except PowerDNSError as exc:
        if exc.status_code != 404:
            raise
        zone = client.create_zone_with_nameservers(
            domain_name,
            [settings.nameserver_1, settings.nameserver_2],
        )
    return client.reconcile_authority(domain_name) if zone else client.get_zone(domain_name)


def reconcile_mail_dns(
    db: Session,
    domain: Domain,
    actor_user_id: UUID,
    *,
    client: PowerDNSClient | None = None,
) -> MailDNSReconcileResult:
    if domain.status != DomainStatus.verified or domain.ownership_verified_at is None:
        raise MailDNSReconcileError("Domain ownership must be verified before mail DNS can be reconciled")
    if domain.dns_mode != DomainDnsMode.platform:
        raise MailDNSReconcileError("Automatic mail DNS reconciliation is only available for platform-hosted DNS")
    if not domain.mail_enabled:
        raise MailDNSReconcileError("Mail must be enabled before mail DNS can be reconciled")

    key, created = _ensure_active_key(db, domain, actor_user_id)

    try:
        synced = sync_active_dkim_keys(db)
    except Exception as exc:
        raise MailDNSReconcileError("Rspamd DKIM signing synchronization failed") from exc

    dns = client or PowerDNSClient()
    try:
        zone = _zone_or_create(dns, domain.ascii_name)
        desired = recommended_records(
            domain.ascii_name,
            settings.mail_hostname,
            key.selector,
            key.public_key_b64,
        )
        published: list[dict] = []
        for record in desired:
            fqdn, rtype, contents = validate_record(
                domain.ascii_name,
                record["name"],
                record["type"],
                [record["value"]],
            )

            # SPF shares the apex TXT RRset with unrelated customer records.
            # Preserve non-SPF TXT values while ensuring exactly one platform
            # SPF policy is present. Dedicated MX/DKIM/DMARC RRsets are owned by
            # the mail service when mail is enabled on platform-hosted DNS.
            if record["purpose"] == "spf":
                existing = _existing_rrset_contents(zone, fqdn, rtype)
                preserved = [
                    value
                    for value in existing
                    if not _strip_txt_quotes(value).lower().startswith("v=spf1")
                ]
                contents = preserved + contents

            dns.replace_rrset(
                domain.ascii_name,
                fqdn,
                rtype,
                settings.powerdns_default_ttl,
                contents,
            )
            published.append(
                {
                    "name": fqdn,
                    "type": rtype,
                    "values": contents,
                    "purpose": record["purpose"],
                }
            )
        dns.rectify_zone(domain.ascii_name)
    except (PowerDNSError, ValueError) as exc:
        raise MailDNSReconcileError(f"PowerDNS mail record reconciliation failed: {exc}") from exc

    return MailDNSReconcileResult(
        domain=domain.ascii_name,
        selector=key.selector,
        dkim_created=created,
        rspamd_synced_domains=synced,
        records=published,
    )
