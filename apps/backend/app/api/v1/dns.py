from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.models.domains import DomainDnsMode, DomainStatus
from app.api.v1.domains import _audit, _domain_or_404
from app.services.domains import add_domain_event
from app.services.mail_dns_reconcile import MailDNSReconcileError, reconcile_mail_dns
from app.services.powerdns import PowerDNSClient, PowerDNSError, validate_record

router = APIRouter(prefix="/tenants/{tenant_id}/domains/{domain_id}/dns", tags=["dns"])


def _platform_domain(db: Session, tenant_id: UUID, domain_id: UUID):
    """Return a non-archived domain that is configured for Mailbox DNS.

    Pending platform domains are intentionally allowed here so operators can
    stage an authoritative PowerDNS zone and copy/import records before changing
    registrar delegation. Until ownership is verified, no mail lifecycle is
    reconciled and the zone is only useful if the owner later delegates to it.
    """
    domain = _domain_or_404(db, tenant_id, domain_id)
    if domain.dns_mode != DomainDnsMode.platform:
        raise HTTPException(409, "Domain is configured for external DNS")
    if domain.status == DomainStatus.archived:
        raise HTTPException(409, "Archived domains cannot manage DNS")
    return domain


def _verified_platform_domain(db: Session, tenant_id: UUID, domain_id: UUID):
    domain = _platform_domain(db, tenant_id, domain_id)
    if domain.status != DomainStatus.verified or domain.ownership_verified_at is None:
        raise HTTPException(409, "Domain ownership must be verified before live mail/DNS activation")
    return domain


def _managed_domain(db: Session, tenant_id: UUID, domain_id: UUID):
    """Compatibility helper for DNSSEC/templates that must stay verified-only."""
    return _verified_platform_domain(db, tenant_id, domain_id)


def _is_verified(domain) -> bool:
    return domain.status == DomainStatus.verified and domain.ownership_verified_at is not None


def _pdns_error(exc: PowerDNSError):
    raise HTTPException(status_code=502, detail=str(exc)) from exc


def _mail_dns_or_502(db: Session, domain, current: User):
    try:
        result = reconcile_mail_dns(db, domain, current.id)
    except MailDNSReconcileError as exc:
        add_domain_event(db, domain, current.id, "mail.dns_reconcile_failed", {"detail": str(exc)})
        _audit(db, domain.tenant_id, current, "deliverability.mail_dns.reconcile_failed", domain, {"detail": str(exc)})
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    add_domain_event(
        db,
        domain,
        current.id,
        "mail.dns_reconciled",
        {"selector": result.selector, "dkim_created": result.dkim_created, "record_count": len(result.records)},
    )
    _audit(
        db,
        domain.tenant_id,
        current,
        "deliverability.mail_dns.reconcile",
        domain,
        {"selector": result.selector, "dkim_created": result.dkim_created, "record_count": len(result.records)},
    )
    db.commit()
    return result


@router.get("/health")
def dns_health(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    _platform_domain(db, tenant_id, domain_id)
    try:
        server = PowerDNSClient().health()
        return {"available": True, "server_id": server.get("id"), "version": server.get("version")}
    except PowerDNSError as exc:
        _pdns_error(exc)


@router.post("/zone", status_code=status.HTTP_201_CREATED)
def provision_zone(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _platform_domain(db, tenant_id, domain_id)
    verified = _is_verified(domain)
    client = PowerDNSClient()
    try:
        try:
            client.get_zone(domain.ascii_name)
            created = False
            zone = client.reconcile_authority(domain.ascii_name)
        except PowerDNSError as exc:
            if exc.status_code != 404 and "HTTP 404" not in str(exc):
                raise
            zone = client.create_zone(domain.ascii_name)
            created = True
    except (PowerDNSError, ValueError) as exc:
        if isinstance(exc, PowerDNSError):
            _pdns_error(exc)
        raise HTTPException(422, detail=str(exc)) from exc

    # A pending domain may have its zone and ordinary records staged, but mail
    # routing/DKIM/Rspamd lifecycle is not activated until ownership is proven.
    mail_dns = None
    if verified and domain.mail_enabled:
        result = _mail_dns_or_502(db, domain, current)
        mail_dns = {
            "selector": result.selector,
            "dkim_created": result.dkim_created,
            "record_count": len(result.records),
            "rspamd_synced_domains": result.rspamd_synced_domains,
        }

    # Use the established zone lifecycle event names for both staged and verified
    # zones. Domain release safety already treats these events as evidence that a
    # PowerDNS zone exists, preventing an abandoned staged zone from being
    # silently orphaned. Audit metadata still distinguishes staged from live.
    event_type = "dns.zone_provisioned" if created else "dns.zone_reconciled"
    audit_action = "dns.zone.provision" if verified else "dns.zone.stage"
    add_domain_event(db, domain, current.id, event_type, {"created": created, "verified": verified, "staged": not verified})
    _audit(
        db,
        tenant_id,
        current,
        audit_action,
        domain,
        {"created": created, "staged": not verified, "mail_dns_reconciled": bool(mail_dns)},
    )
    db.commit()
    return {
        "created": created,
        "zone": zone,
        "staged": not verified,
        "ownership_verified": verified,
        "activation_required": not verified,
        "required_nameservers": [settings.nameserver_1, settings.nameserver_2],
        "mail_dns": mail_dns,
    }


@router.post("/mail/reconcile")
def reconcile_mail_records(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _verified_platform_domain(db, tenant_id, domain_id)
    if not domain.mail_enabled:
        raise HTTPException(status_code=409, detail="Mail is disabled for this domain")
    result = _mail_dns_or_502(db, domain, current)
    return {
        "domain": result.domain,
        "selector": result.selector,
        "dkim_created": result.dkim_created,
        "rspamd_synced_domains": result.rspamd_synced_domains,
        "records": result.records,
    }


@router.get("/zone")
def get_zone(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    domain = _platform_domain(db, tenant_id, domain_id)
    try:
        return PowerDNSClient().get_zone(domain.ascii_name)
    except PowerDNSError as exc:
        if exc.status_code == 404 or "HTTP 404" in str(exc):
            raise HTTPException(status_code=404, detail="Authoritative zone has not been prepared yet") from exc
        _pdns_error(exc)


@router.put("/records")
def replace_record(
    tenant_id: UUID,
    domain_id: UUID,
    payload: dict,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _platform_domain(db, tenant_id, domain_id)
    try:
        name, rtype, contents = validate_record(
            domain.ascii_name,
            str(payload.get("name", "@")),
            str(payload.get("type", "")),
            payload.get("contents") or [],
        )
        ttl = int(payload.get("ttl", settings.powerdns_default_ttl))
        if not 60 <= ttl <= 86400:
            raise ValueError("TTL must be between 60 and 86400 seconds")
        PowerDNSClient().replace_rrset(domain.ascii_name, name, rtype, ttl, contents)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except PowerDNSError as exc:
        _pdns_error(exc)
    event_type = "dns.rrset_replaced" if _is_verified(domain) else "dns.staged_rrset_replaced"
    add_domain_event(db, domain, current.id, event_type, {"name": name, "type": rtype, "ttl": ttl, "value_count": len(contents)})
    _audit(db, tenant_id, current, "dns.record.replace", domain, {"name": name, "type": rtype, "ttl": ttl, "staged": not _is_verified(domain)})
    db.commit()
    return {"name": name, "type": rtype, "ttl": ttl, "contents": contents, "staged": not _is_verified(domain)}


@router.delete("/records", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    tenant_id: UUID,
    domain_id: UUID,
    name: str = Query(...),
    record_type: str = Query(..., alias="type"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _platform_domain(db, tenant_id, domain_id)
    try:
        fqdn, rtype, _ = validate_record(domain.ascii_name, name, record_type, ["placeholder"])
        if rtype in {"A", "AAAA"}:
            fqdn = __import__("app.services.powerdns", fromlist=["normalize_record_name"]).normalize_record_name(domain.ascii_name, name)
        PowerDNSClient().delete_rrset(domain.ascii_name, fqdn, rtype)
    except ValueError as exc:
        from app.services.powerdns import normalize_record_name
        rtype = record_type.upper()
        if rtype not in {"A", "AAAA", "CNAME", "MX", "TXT", "CAA", "SRV"}:
            raise HTTPException(422, detail="Unsupported record type") from exc
        fqdn = normalize_record_name(domain.ascii_name, name)
        if fqdn != domain.ascii_name and not fqdn.endswith("." + domain.ascii_name):
            raise HTTPException(422, detail="Record name must be inside the managed zone") from exc
        try:
            PowerDNSClient().delete_rrset(domain.ascii_name, fqdn, rtype)
        except PowerDNSError as pdns_exc:
            _pdns_error(pdns_exc)
    except PowerDNSError as exc:
        _pdns_error(exc)
    event_type = "dns.rrset_deleted" if _is_verified(domain) else "dns.staged_rrset_deleted"
    add_domain_event(db, domain, current.id, event_type, {"name": fqdn, "type": rtype})
    _audit(db, tenant_id, current, "dns.record.delete", domain, {"name": fqdn, "type": rtype, "staged": not _is_verified(domain)})
    db.commit()
    return Response(status_code=204)
