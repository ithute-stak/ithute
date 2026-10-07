from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.api.v1.domains import _audit
from app.api.v1.dns import _managed_domain
from app.db.session import get_db
from app.models import User
from app.services.dns_phase5 import delegation_diagnostics, dns_templates
from app.services.domains import add_domain_event
from app.services.powerdns import PowerDNSClient, PowerDNSError
from app.services.registrar_dnssec import DSRecord, OPENSRS_DNSSEC_ALGORITHMS, OpenSRSRegistrar, RegistrarError, preferred_ds

router = APIRouter(prefix="/tenants/{tenant_id}/domains/{domain_id}/dns", tags=["dns-security"])


def _pdns_error(exc: PowerDNSError):
    raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/dnssec")
def dnssec_status(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    client = PowerDNSClient()
    try:
        zone = client.get_zone(domain.ascii_name)
        keys = client.list_cryptokeys(domain.ascii_name)
    except PowerDNSError as exc:
        _pdns_error(exc)
    ds = []
    for key in keys:
        for value in key.get("ds") or []:
            if value not in ds:
                ds.append(value)
    return {
        "enabled": bool(zone.get("dnssec")),
        "api_rectify": bool(zone.get("api_rectify")),
        "keys": [{k: key.get(k) for k in ("id", "keytype", "active", "published", "dnskey", "ds", "algorithm", "bits")} for key in keys],
        "ds_records": ds,
    }


@router.post("/dnssec/enable")
def enable_dnssec(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    client = PowerDNSClient()
    try:
        zone = client.set_dnssec(domain.ascii_name, True)
        keys = client.list_cryptokeys(domain.ascii_name)
    except PowerDNSError as exc:
        _pdns_error(exc)
    add_domain_event(db, domain, current.id, "dns.dnssec_enabled")
    _audit(db, tenant_id, current, "dns.dnssec.enable", domain, {})
    db.commit()
    ds = [value for key in keys for value in (key.get("ds") or [])]
    return {"enabled": bool(zone.get("dnssec")), "ds_records": ds, "registrar_action_required": bool(ds)}


@router.get("/parent-ds")
def parent_ds_status(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    client = PowerDNSClient()
    try:
        keys = client.list_cryptokeys(domain.ascii_name)
    except PowerDNSError as exc:
        _pdns_error(exc)
    ds_values = [value for key in keys for value in (key.get("ds") or [])]
    selected = preferred_ds(ds_values)
    compatible = preferred_ds(ds_values, allowed_algorithms=OPENSRS_DNSSEC_ALGORITHMS)
    registrar = OpenSRSRegistrar()
    result = {
        "provider": "opensrs",
        "configured": registrar.configured,
        "domain": domain.ascii_name,
        "recommended": (compatible or selected).as_opensrs() if (compatible or selected) else None,
        "recommended_text": (compatible or selected).text() if (compatible or selected) else None,
        "registrar_compatible": compatible is not None,
        "auto_prepare_supported": True,
        "registrar_records": [],
    }
    if registrar.configured:
        try:
            result["registrar_records"] = [record.as_opensrs() for record in registrar.get_dnssec(domain.ascii_name)]
        except RegistrarError as exc:
            result["provider_error"] = str(exc)
    return result


@router.post("/parent-ds/publish")
def publish_parent_ds(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    registrar = OpenSRSRegistrar()
    if not registrar.configured:
        raise HTTPException(409, "OpenSRS registrar integration is not configured. Configure OPENSRS_USERNAME and OPENSRS_API_KEY first.")
    try:
        client = PowerDNSClient()
        zone = client.get_zone(domain.ascii_name)
        if not zone.get("dnssec"):
            raise HTTPException(409, "Enable DNSSEC signing before publishing a parent DS record")
        keys = client.list_cryptokeys(domain.ascii_name)
        ds_values = [value for key in keys for value in (key.get("ds") or [])]
        selected = preferred_ds(ds_values, allowed_algorithms=OPENSRS_DNSSEC_ALGORITHMS)
        generated_compatible_key = False
        if selected is None:
            # Keep the existing signing material in place and add a registrar-compatible
            # KSK. This avoids a destructive algorithm cutover while allowing the parent
            # registry to establish a valid chain of trust.
            client.create_cryptokey(
                domain.ascii_name,
                keytype="ksk",
                algorithm="rsasha256",
                bits=2048,
                active=True,
                published=True,
            )
            client.rectify_zone(domain.ascii_name)
            keys = client.list_cryptokeys(domain.ascii_name)
            ds_values = [value for key in keys for value in (key.get("ds") or [])]
            selected = preferred_ds(ds_values, allowed_algorithms=OPENSRS_DNSSEC_ALGORITHMS)
            generated_compatible_key = True
        if selected is None:
            raise HTTPException(409, "PowerDNS could not produce a registrar-compatible DS record")
        records = registrar.publish(domain.ascii_name, selected)
    except PowerDNSError as exc:
        _pdns_error(exc)
    except RegistrarError as exc:
        raise HTTPException(502, str(exc)) from exc
    add_domain_event(db, domain, current.id, "dns.parent_ds_publish_requested", {"provider": "opensrs", "ds": selected.text(), "generated_compatible_key": generated_compatible_key})
    _audit(db, tenant_id, current, "dns.parent_ds.publish", domain, {"provider": "opensrs", "ds": selected.text(), "generated_compatible_key": generated_compatible_key})
    db.commit()
    return {"published": True, "provider": "opensrs", "selected": selected.as_opensrs(), "generated_compatible_key": generated_compatible_key, "registrar_records": [record.as_opensrs() for record in records]}


@router.post("/parent-ds/remove")
def remove_parent_ds(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    registrar = OpenSRSRegistrar()
    if not registrar.configured:
        raise HTTPException(409, "OpenSRS registrar integration is not configured")
    try:
        keys = PowerDNSClient().list_cryptokeys(domain.ascii_name)
        managed = []
        for value in [value for key in keys for value in (key.get("ds") or [])]:
            try:
                managed.append(DSRecord.parse(value))
            except ValueError:
                continue
        remaining = registrar.remove_managed(domain.ascii_name, managed)
    except PowerDNSError as exc:
        _pdns_error(exc)
    except RegistrarError as exc:
        raise HTTPException(502, str(exc)) from exc
    add_domain_event(db, domain, current.id, "dns.parent_ds_remove_requested", {"provider": "opensrs", "managed_removed": len(managed)})
    _audit(db, tenant_id, current, "dns.parent_ds.remove", domain, {"provider": "opensrs", "managed_removed": len(managed)})
    db.commit()
    return {"removed": True, "provider": "opensrs", "registrar_records": [record.as_opensrs() for record in remaining]}


@router.post("/dnssec/disable")
def disable_dnssec(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    # Disabling signing before removing a parent DS can break validation. The client must explicitly remove DS first.
    diagnostics = delegation_diagnostics(domain.ascii_name)
    if diagnostics.get("parent_ds_present"):
        raise HTTPException(409, "Remove the DS record at the registrar/parent zone before disabling DNSSEC")
    try:
        zone = PowerDNSClient().set_dnssec(domain.ascii_name, False)
    except PowerDNSError as exc:
        _pdns_error(exc)
    add_domain_event(db, domain, current.id, "dns.dnssec_disabled")
    _audit(db, tenant_id, current, "dns.dnssec.disable", domain, {})
    db.commit()
    return {"enabled": bool(zone.get("dnssec"))}


@router.get("/diagnostics")
def diagnostics(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    result = delegation_diagnostics(domain.ascii_name)
    try:
        zone = PowerDNSClient().get_zone(domain.ascii_name)
        result["authoritative_zone"] = {
            "available": True,
            "kind": zone.get("kind"),
            "serial": zone.get("serial"),
            "dnssec": zone.get("dnssec"),
        }
    except PowerDNSError as exc:
        result["authoritative_zone"] = {"available": False, "error": str(exc)}
    return result


@router.get("/templates")
def list_templates(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    return [template.__dict__ for template in dns_templates(domain.ascii_name)]


@router.post("/templates/{template_name}")
def apply_template(template_name: str, tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _managed_domain(db, tenant_id, domain_id)
    templates = {template.name: template for template in dns_templates(domain.ascii_name)}
    template = templates.get(template_name)
    if not template:
        raise HTTPException(404, "DNS template not found")
    client = PowerDNSClient()
    try:
        for record in template.records:
            name = domain.ascii_name if record["name"] == "@" else f'{record["name"]}.{domain.ascii_name}'
            client.replace_rrset(domain.ascii_name, name, record["type"], record["ttl"], record["contents"])
    except PowerDNSError as exc:
        _pdns_error(exc)
    add_domain_event(db, domain, current.id, "dns.template_applied", {"template": template.name})
    _audit(db, tenant_id, current, "dns.template.apply", domain, {"template": template.name})
    db.commit()
    return {"applied": True, "template": template.__dict__}
