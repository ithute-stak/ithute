from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.core.config import settings
from app.db.session import get_db
from app.models import AuditLog, Domain, PlatformConfiguration, User
from app.services.platform_setup import (
    PlatformSetupError,
    activate_caddy,
    normalize_platform_domain,
    platform_names,
    validate_public_ip,
    verify_public_delegation,
)
from app.services.powerdns import PowerDNSClient, PowerDNSError

router = APIRouter(tags=["platform-setup"])


class PlatformDomainRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=253)
    acme_email: EmailStr
    nameserver_2_ip: str | None = None


def _configuration(db: Session, create: bool = True) -> PlatformConfiguration | None:
    row = db.get(PlatformConfiguration, 1)
    if row is None and create:
        bootstrap_ip = settings.bootstrap_public_ip or settings.mail_public_ip
        row = PlatformConfiguration(id=1, bootstrap_public_ip=bootstrap_ip, mode="bootstrap", security_level="bootstrap")
        db.add(row)
        db.flush()
    return row


def _audit(db: Session, current: User, action: str, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            actor_user_id=current.id,
            action=action,
            resource_type="platform_configuration",
            resource_id="1",
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


def _status(row: PlatformConfiguration | None, *, public: bool = False) -> dict:
    mode = row.mode if row else "bootstrap"
    active = mode == "domain_active"
    signup_ready = active and bool(settings.system_email_from and settings.system_smtp_host)
    result = {
        "mode": mode,
        "security_level": row.security_level if row else "bootstrap",
        "signup_enabled": settings.environment.lower() != "production" or signup_ready,
        "setup_required": not active,
    }
    if public:
        if active and row and row.panel_hostname:
            result["panel_url"] = f"https://{row.panel_hostname}"
        return result
    if row is None:
        return result
    result.update(
        {
            "bootstrap_public_ip": row.bootstrap_public_ip,
            "primary_domain": row.primary_domain,
            "panel_hostname": row.panel_hostname,
            "api_hostname": row.api_hostname,
            "groupware_hostname": row.groupware_hostname,
            "mail_hostname": row.mail_hostname,
            "nameserver_1": row.nameserver_1,
            "nameserver_2": row.nameserver_2,
            "nameserver_1_ip": row.nameserver_1_ip,
            "nameserver_2_ip": row.nameserver_2_ip,
            "acme_email": row.acme_email,
            "dns_zone_provisioned_at": row.dns_zone_provisioned_at,
            "delegation_verified_at": row.delegation_verified_at,
            "activated_at": row.activated_at,
            "security": {
                "owner_mfa_required_for_activation": True,
                "https_active": active,
                "hsts_active": active,
                "secure_cookies_on_https": True,
                "public_signup_rate_limit": "redis-fail-closed",
                "email_verification_required": True,
                "external_captcha_provider": None,
            },
        }
    )
    if row.primary_domain:
        result["registrar_instructions"] = {
            "glue_records": [
                {"hostname": row.nameserver_1, "ip": row.nameserver_1_ip},
                {"hostname": row.nameserver_2, "ip": row.nameserver_2_ip},
            ],
            "delegate_nameservers": [row.nameserver_1, row.nameserver_2],
            "reverse_dns": {
                "ip": row.bootstrap_public_ip,
                "ptr": row.mail_hostname,
                "note": "Set PTR/reverse DNS at the VPS or IP provider; authoritative DNS cannot create the parent reverse record.",
            },
        }
        if row.nameserver_1_ip == row.nameserver_2_ip:
            result["redundancy_warning"] = "ns1 and ns2 currently share one public IP. Move ns2 to an independent failure domain before production DNS SLA use."
    return result


@router.get("/public/platform-mode")
def public_platform_mode(db: Session = Depends(get_db)):
    return _status(_configuration(db, create=False), public=True)


@router.get("/platform/setup")
def platform_setup_status(
    db: Session = Depends(get_db), current: User = Depends(require_platform_owner)
):
    row = _configuration(db)
    db.commit()
    db.refresh(row)
    return _status(row)


@router.post("/platform/setup/domain")
def configure_platform_domain(
    payload: PlatformDomainRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    try:
        domain = normalize_platform_domain(payload.domain)
        names = platform_names(domain)
        row = _configuration(db)
        primary_ip = validate_public_ip(row.bootstrap_public_ip or settings.bootstrap_public_ip or settings.mail_public_ip or "", "Bootstrap public IP")
        ns2_ip = validate_public_ip(payload.nameserver_2_ip or primary_ip, "ns2 public IP")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    tenant_domain = db.scalar(select(Domain).where(Domain.ascii_name == domain))
    if tenant_domain:
        raise HTTPException(status_code=409, detail="This domain is already registered as a tenant domain; remove that assignment before using it as the platform domain")
    if row.primary_domain and row.primary_domain != domain and row.mode == "domain_active":
        raise HTTPException(status_code=409, detail="The active platform domain cannot be replaced from bootstrap setup")

    client = PowerDNSClient()
    try:
        try:
            client.get_zone(domain)
        except PowerDNSError as exc:
            if exc.status_code != 404 and "HTTP 404" not in str(exc):
                raise
            client.create_zone_with_nameservers(domain, [names.ns1, names.ns2])

        ttl = settings.powerdns_default_ttl
        client.replace_rrset(domain, domain, "NS", ttl, [f"{names.ns1}.", f"{names.ns2}."])
        for hostname in (names.panel, names.api, names.groupware, names.mail, names.ns1):
            client.replace_rrset(domain, hostname, "A", ttl, [primary_ip])
        client.replace_rrset(domain, names.ns2, "A", ttl, [ns2_ip])
        client.replace_rrset(domain, domain, "MX", ttl, [f"10 {names.mail}."])
        client.replace_rrset(domain, domain, "TXT", ttl, ['"v=spf1 mx -all"'])
        client.replace_rrset(domain, f"_dmarc.{domain}", "TXT", ttl, [f'"v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}"'])
        client.replace_rrset(domain, domain, "CAA", ttl, ['0 issue "letsencrypt.org"'])
        client.replace_rrset(domain, f"_submission._tcp.{domain}", "SRV", ttl, [f"0 1 587 {names.mail}."])
        client.replace_rrset(domain, f"_imaps._tcp.{domain}", "SRV", ttl, [f"0 1 993 {names.mail}."])
        client.rectify_zone(domain)
    except (PowerDNSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Authoritative DNS provisioning failed: {exc}") from exc

    now = datetime.now(timezone.utc)
    row.mode = "domain_pending"
    row.security_level = "bootstrap"
    row.bootstrap_public_ip = primary_ip
    row.primary_domain = domain
    row.panel_hostname = names.panel
    row.api_hostname = names.api
    row.groupware_hostname = names.groupware
    row.mail_hostname = names.mail
    row.nameserver_1 = names.ns1
    row.nameserver_2 = names.ns2
    row.nameserver_1_ip = primary_ip
    row.nameserver_2_ip = ns2_ip
    row.acme_email = str(payload.acme_email).lower()
    row.dns_zone_provisioned_at = now
    row.delegation_verified_at = None
    row.activated_at = None
    row.updated_by_user_id = current.id
    _audit(db, current, "platform.domain.configure", {"domain": domain, "ns2_independent": ns2_ip != primary_ip})
    db.commit()
    db.refresh(row)
    return _status(row)


@router.post("/platform/setup/verify")
def verify_platform_domain(
    db: Session = Depends(get_db), current: User = Depends(require_platform_owner)
):
    row = _configuration(db)
    if not row.primary_domain or not row.nameserver_1_ip or not row.nameserver_2_ip:
        raise HTTPException(status_code=409, detail="Configure the platform domain before verifying delegation")
    names = platform_names(row.primary_domain)
    result = verify_public_delegation(names, row.nameserver_1_ip, row.nameserver_2_ip)
    if result["verified"]:
        row.mode = "domain_verified"
        row.delegation_verified_at = datetime.now(timezone.utc)
    else:
        row.mode = "domain_pending"
        row.delegation_verified_at = None
    row.updated_by_user_id = current.id
    _audit(db, current, "platform.domain.verify", {"verified": result["verified"]})
    db.commit()
    db.refresh(row)
    return {**_status(row), "verification": result}


@router.post("/platform/setup/activate")
def activate_platform_domain(
    db: Session = Depends(get_db), current: User = Depends(require_platform_owner)
):
    if not current.mfa_enabled:
        raise HTTPException(status_code=409, detail="Enable MFA on the platform-owner account before activating the public platform domain")
    row = _configuration(db)
    if not row.primary_domain or not row.acme_email or not row.nameserver_1_ip or not row.nameserver_2_ip:
        raise HTTPException(status_code=409, detail="Configure the platform domain first")

    names = platform_names(row.primary_domain)
    verification = verify_public_delegation(names, row.nameserver_1_ip, row.nameserver_2_ip)
    if not verification["verified"]:
        row.mode = "domain_pending"
        row.delegation_verified_at = None
        db.commit()
        raise HTTPException(status_code=409, detail="Public DNS delegation is not verified yet; complete registrar glue/delegation before activation")

    try:
        activate_caddy(names, row.bootstrap_public_ip or row.nameserver_1_ip, row.acme_email)
    except (PlatformSetupError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    row.mode = "domain_active"
    row.security_level = "hardened"
    row.delegation_verified_at = row.delegation_verified_at or now
    row.activated_at = now
    row.updated_by_user_id = current.id
    _audit(db, current, "platform.domain.activate", {"domain": row.primary_domain, "https": True, "hsts": True, "owner_mfa": True})
    db.commit()
    db.refresh(row)
    return {
        **_status(row),
        "urls": {
            "panel": f"https://{row.panel_hostname}",
            "api": f"https://{row.api_hostname}",
            "groupware": f"https://{row.groupware_hostname}",
        },
        "verification": verification,
    }
