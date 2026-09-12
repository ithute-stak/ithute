from __future__ import annotations

import json
import re
from uuid import UUID
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.api.v1.domains import _audit, _domain_or_404
from app.db.session import get_db
from app.models import DnsZoneAnalyticsSnapshot, EdgeApplication, EdgeInspection, EdgeOrigin, EdgeRule, User
from app.models.domains import DomainStatus
from app.services.edge_inspection import EdgeInspectionError, inspect_public_origin, summarize_powerdns_zone
from app.services.powerdns import PowerDNSClient, PowerDNSError

router = APIRouter(prefix="/tenants/{tenant_id}/edge", tags=["edge-security"])

_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_RULE_TYPES = {"firewall", "rate_limit", "cache", "redirect", "header", "access", "api_shield", "bot"}
_RULE_ACTIONS = {"allow", "block", "log", "challenge", "throttle", "cache", "bypass_cache", "redirect", "set_header", "require_access"}
_TLS_VERSIONS = {"TLSv1.2", "TLSv1.3"}


class ApplicationCreate(BaseModel):
    domain_id: UUID
    hostname: str = Field(min_length=1, max_length=253)
    mode: str = "dns_only"


class ApplicationUpdate(BaseModel):
    mode: str | None = None
    enabled: bool | None = None
    cache_enabled: bool | None = None
    waf_enabled: bool | None = None
    bot_protection_enabled: bool | None = None
    api_shield_enabled: bool | None = None
    access_enabled: bool | None = None
    rate_limit_per_minute: int | None = None
    tls_mode: str | None = None
    minimum_tls_version: str | None = None
    health_path: str | None = None
    expected_status: int | None = None


class OriginCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=1000)
    enabled: bool = True
    weight: int = 100
    failover_priority: int = 1
    health_path: str = "/"
    expected_status: int = 200
    timeout_seconds: int = 5


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    rule_type: str
    expression: str = "true"
    action: str
    config: dict = Field(default_factory=dict)
    priority: int = 100
    enabled: bool = True


def _hostname(value: str, zone: str) -> str:
    host = value.strip().rstrip(".").lower()
    if host in {"", "@"}:
        host = zone.lower().rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise HTTPException(422, "Invalid edge hostname") from exc
    labels = host.split(".")
    if len(host) > 253 or any(not part or len(part) > 63 or not _HOST_LABEL.fullmatch(part) for part in labels):
        raise HTTPException(422, "Invalid edge hostname")
    zone = zone.lower().rstrip(".")
    if host != zone and not host.endswith("." + zone):
        raise HTTPException(422, "Edge hostname must be inside the selected managed domain")
    return host


def _health_path(value: str) -> str:
    path = value.strip() or "/"
    if not path.startswith("/") or "\r" in path or "\n" in path or len(path) > 500:
        raise HTTPException(422, "Health path must be a relative URL path starting with /")
    return path


def _validate_origin_payload(payload: OriginCreate) -> None:
    parsed = urlsplit(payload.url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(422, "Origin URL must be an http(s) URL with a hostname and no credentials or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(422, "Origin URL contains an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise HTTPException(422, "Origin port is invalid")
    if not 1 <= payload.weight <= 10000 or not 1 <= payload.failover_priority <= 10000:
        raise HTTPException(422, "Origin weight and failover priority must be between 1 and 10000")
    if not 100 <= payload.expected_status <= 599 or not 1 <= payload.timeout_seconds <= 30:
        raise HTTPException(422, "Origin health settings are outside allowed ranges")
    _health_path(payload.health_path)


def _application_or_404(db: Session, tenant_id: UUID, app_id: UUID) -> EdgeApplication:
    app = db.scalar(select(EdgeApplication).where(EdgeApplication.id == app_id, EdgeApplication.tenant_id == tenant_id))
    if not app:
        raise HTTPException(404, "Edge application not found")
    return app


def _application_dict(db: Session, app: EdgeApplication) -> dict:
    origins = db.scalars(select(EdgeOrigin).where(EdgeOrigin.application_id == app.id).order_by(EdgeOrigin.failover_priority, EdgeOrigin.name)).all()
    rules = db.scalars(select(EdgeRule).where(EdgeRule.application_id == app.id).order_by(EdgeRule.priority, EdgeRule.created_at)).all()
    latest = db.scalar(select(EdgeInspection).where(EdgeInspection.application_id == app.id).order_by(EdgeInspection.checked_at.desc()).limit(1))
    return {
        "id": app.id,
        "tenant_id": app.tenant_id,
        "domain_id": app.domain_id,
        "hostname": app.hostname,
        "mode": app.mode,
        "enabled": app.enabled,
        "cache_enabled": app.cache_enabled,
        "waf_enabled": app.waf_enabled,
        "bot_protection_enabled": app.bot_protection_enabled,
        "api_shield_enabled": app.api_shield_enabled,
        "access_enabled": app.access_enabled,
        "rate_limit_per_minute": app.rate_limit_per_minute,
        "tls_mode": app.tls_mode,
        "minimum_tls_version": app.minimum_tls_version,
        "health_path": app.health_path,
        "expected_status": app.expected_status,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
        "origins": [
            {
                "id": item.id, "name": item.name, "url": item.url, "enabled": item.enabled,
                "weight": item.weight, "failover_priority": item.failover_priority,
                "health_path": item.health_path, "expected_status": item.expected_status,
                "timeout_seconds": item.timeout_seconds,
            }
            for item in origins
        ],
        "rules": [
            {
                "id": item.id, "name": item.name, "rule_type": item.rule_type,
                "expression": item.expression, "action": item.action,
                "config": json.loads(item.config_json or "{}"), "priority": item.priority, "enabled": item.enabled,
            }
            for item in rules
        ],
        "latest_inspection": None if latest is None else _inspection_dict(latest),
    }


def _inspection_dict(item: EdgeInspection) -> dict:
    return {
        "id": item.id,
        "origin_id": item.origin_id,
        "checked_at": item.checked_at,
        "healthy": item.healthy,
        "resolved_ip": item.resolved_ip,
        "status_code": item.status_code,
        "latency_ms": item.latency_ms,
        "tls_version": item.tls_version,
        "cipher": item.cipher,
        "certificate_issuer": item.certificate_issuer,
        "certificate_not_after": item.certificate_not_after,
        "certificate_days_remaining": item.certificate_days_remaining,
        "error": item.error,
    }


@router.get("/capabilities")
def capabilities(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    return {
        "phase": "edge-security-1",
        "capabilities": {
            "dns_zone_analytics": {"state": "active", "detail": "Live PowerDNS zone inventory snapshots and history"},
            "origin_health": {"state": "active", "detail": "SSRF-safe public HTTP(S) health probes"},
            "tls_certificate_monitoring": {"state": "active", "detail": "TLS protocol, cipher, issuer and certificate expiry inspection"},
            "reverse_proxy": {"state": "control_plane", "detail": "Protected-mode policy can be configured; distributed edge enforcement is the next runtime phase"},
            "waf": {"state": "control_plane", "detail": "WAF policy and firewall rules can be configured; runtime enforcement is the next phase"},
            "rate_limiting": {"state": "control_plane", "detail": "Application and rule limits are stored for edge runtime enforcement"},
            "cache": {"state": "control_plane", "detail": "Caching policy is stored for edge runtime enforcement"},
            "load_balancing": {"state": "control_plane", "detail": "Weighted/failover origin pools and health are available; traffic steering follows in the runtime phase"},
            "api_shield": {"state": "control_plane", "detail": "API protection policy is modeled for runtime enforcement"},
            "bot_protection": {"state": "control_plane", "detail": "Bot protection policy is modeled for runtime enforcement"},
            "zero_trust_access": {"state": "planned", "detail": "Identity-gated private application access is not active yet"},
            "tunnel": {"state": "planned", "detail": "Outbound private-origin tunnels require a dedicated agent and relay service"},
            "global_cdn": {"state": "planned", "detail": "A global/regional edge node fleet is not claimed by this single-node control plane"},
        },
    }


@router.get("/applications")
def list_applications(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    apps = db.scalars(select(EdgeApplication).where(EdgeApplication.tenant_id == tenant_id).order_by(EdgeApplication.hostname)).all()
    return {"items": [_application_dict(db, app) for app in apps]}


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(tenant_id: UUID, payload: ApplicationCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _domain_or_404(db, tenant_id, payload.domain_id)
    if domain.status != DomainStatus.verified or domain.ownership_verified_at is None:
        raise HTTPException(409, "Verify domain ownership before creating an edge application")
    if payload.mode not in {"dns_only", "protected"}:
        raise HTTPException(422, "Edge mode must be dns_only or protected")
    app = EdgeApplication(tenant_id=tenant_id, domain_id=domain.id, hostname=_hostname(payload.hostname, domain.ascii_name), mode=payload.mode)
    db.add(app)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "An edge application already exists for this hostname") from exc
    _audit(db, tenant_id, current, "edge.application.create", domain, {"hostname": app.hostname, "mode": app.mode})
    db.commit()
    db.refresh(app)
    return _application_dict(db, app)


@router.patch("/applications/{app_id}")
def update_application(tenant_id: UUID, app_id: UUID, payload: ApplicationUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _application_or_404(db, tenant_id, app_id)
    values = payload.model_dump(exclude_unset=True)
    if "mode" in values and values["mode"] not in {"dns_only", "protected"}:
        raise HTTPException(422, "Edge mode must be dns_only or protected")
    if "tls_mode" in values and values["tls_mode"] not in {"automatic", "strict", "origin"}:
        raise HTTPException(422, "TLS mode must be automatic, strict or origin")
    if "minimum_tls_version" in values and values["minimum_tls_version"] not in _TLS_VERSIONS:
        raise HTTPException(422, "Minimum TLS version must be TLSv1.2 or TLSv1.3")
    if "rate_limit_per_minute" in values and values["rate_limit_per_minute"] is not None and not 1 <= values["rate_limit_per_minute"] <= 1_000_000:
        raise HTTPException(422, "Rate limit must be between 1 and 1,000,000 requests per minute")
    if "health_path" in values and values["health_path"] is not None:
        values["health_path"] = _health_path(values["health_path"])
    if "expected_status" in values and values["expected_status"] is not None and not 100 <= values["expected_status"] <= 599:
        raise HTTPException(422, "Expected status must be between 100 and 599")
    for key, value in values.items():
        setattr(app, key, value)
    domain = _domain_or_404(db, tenant_id, app.domain_id)
    _audit(db, tenant_id, current, "edge.application.update", domain, {"hostname": app.hostname, "changes": sorted(values)})
    db.commit()
    db.refresh(app)
    return _application_dict(db, app)


@router.delete("/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(tenant_id: UUID, app_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _application_or_404(db, tenant_id, app_id)
    domain = _domain_or_404(db, tenant_id, app.domain_id)
    _audit(db, tenant_id, current, "edge.application.delete", domain, {"hostname": app.hostname})
    db.delete(app)
    db.commit()
    return Response(status_code=204)


@router.post("/applications/{app_id}/origins", status_code=status.HTTP_201_CREATED)
def create_origin(tenant_id: UUID, app_id: UUID, payload: OriginCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _application_or_404(db, tenant_id, app_id)
    _validate_origin_payload(payload)
    origin = EdgeOrigin(
        application_id=app.id, name=payload.name.strip(), url=payload.url.strip(), enabled=payload.enabled,
        weight=payload.weight, failover_priority=payload.failover_priority, health_path=_health_path(payload.health_path),
        expected_status=payload.expected_status, timeout_seconds=payload.timeout_seconds,
    )
    db.add(origin)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "An origin with this name already exists for the application") from exc
    domain = _domain_or_404(db, tenant_id, app.domain_id)
    _audit(db, tenant_id, current, "edge.origin.create", domain, {"hostname": app.hostname, "origin": origin.name})
    db.commit()
    db.refresh(origin)
    return _application_dict(db, app)


@router.delete("/applications/{app_id}/origins/{origin_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_origin(tenant_id: UUID, app_id: UUID, origin_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _application_or_404(db, tenant_id, app_id)
    origin = db.scalar(select(EdgeOrigin).where(EdgeOrigin.id == origin_id, EdgeOrigin.application_id == app.id))
    if not origin:
        raise HTTPException(404, "Origin not found")
    domain = _domain_or_404(db, tenant_id, app.domain_id)
    _audit(db, tenant_id, current, "edge.origin.delete", domain, {"hostname": app.hostname, "origin": origin.name})
    db.delete(origin)
    db.commit()
    return Response(status_code=204)


@router.post("/applications/{app_id}/rules", status_code=status.HTTP_201_CREATED)
def create_rule(tenant_id: UUID, app_id: UUID, payload: RuleCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _application_or_404(db, tenant_id, app_id)
    rule_type = payload.rule_type.strip().lower()
    action = payload.action.strip().lower()
    if rule_type not in _RULE_TYPES or action not in _RULE_ACTIONS:
        raise HTTPException(422, "Unsupported edge rule type or action")
    if not 1 <= payload.priority <= 100_000 or len(payload.expression) > 4000:
        raise HTTPException(422, "Invalid edge rule priority or expression")
    rule = EdgeRule(
        application_id=app.id, name=payload.name.strip(), rule_type=rule_type, expression=payload.expression.strip() or "true",
        action=action, config_json=json.dumps(payload.config, sort_keys=True), priority=payload.priority, enabled=payload.enabled,
    )
    db.add(rule)
    domain = _domain_or_404(db, tenant_id, app.domain_id)
    _audit(db, tenant_id, current, "edge.rule.create", domain, {"hostname": app.hostname, "rule_type": rule_type, "action": action})
    db.commit()
    db.refresh(rule)
    return _application_dict(db, app)


@router.delete("/applications/{app_id}/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(tenant_id: UUID, app_id: UUID, rule_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _application_or_404(db, tenant_id, app_id)
    rule = db.scalar(select(EdgeRule).where(EdgeRule.id == rule_id, EdgeRule.application_id == app.id))
    if not rule:
        raise HTTPException(404, "Edge rule not found")
    domain = _domain_or_404(db, tenant_id, app.domain_id)
    _audit(db, tenant_id, current, "edge.rule.delete", domain, {"hostname": app.hostname, "rule_type": rule.rule_type})
    db.delete(rule)
    db.commit()
    return Response(status_code=204)


@router.post("/applications/{app_id}/inspect")
def inspect_application(tenant_id: UUID, app_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    app = _application_or_404(db, tenant_id, app_id)
    origins = db.scalars(select(EdgeOrigin).where(EdgeOrigin.application_id == app.id, EdgeOrigin.enabled.is_(True)).order_by(EdgeOrigin.failover_priority, EdgeOrigin.name).limit(10)).all()
    targets = [
        (origin, origin.url, origin.health_path, origin.expected_status, origin.timeout_seconds)
        for origin in origins
    ] or [(None, f"https://{app.hostname}", app.health_path, app.expected_status, 5)]
    results: list[dict] = []
    for origin, url, path, expected, timeout in targets:
        try:
            observed = inspect_public_origin(url, path, expected, timeout)
        except EdgeInspectionError as exc:
            observed = {
                "healthy": False, "resolved_ip": None, "status_code": None, "latency_ms": None,
                "tls_version": None, "cipher": None, "certificate_issuer": None,
                "certificate_not_after": None, "certificate_days_remaining": None, "error": str(exc),
            }
        row = EdgeInspection(application_id=app.id, origin_id=origin.id if origin else None, **observed)
        db.add(row)
        db.flush()
        results.append({"origin": origin.name if origin else app.hostname, **_inspection_dict(row)})
    domain = _domain_or_404(db, tenant_id, app.domain_id)
    _audit(db, tenant_id, current, "edge.application.inspect", domain, {"hostname": app.hostname, "targets": len(results)})
    db.commit()
    return {"application_id": app.id, "hostname": app.hostname, "results": results}


@router.get("/applications/{app_id}/inspections")
def inspections(tenant_id: UUID, app_id: UUID, limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    app = _application_or_404(db, tenant_id, app_id)
    items = db.scalars(select(EdgeInspection).where(EdgeInspection.application_id == app.id).order_by(EdgeInspection.checked_at.desc()).limit(limit)).all()
    return {"items": [_inspection_dict(item) for item in items]}


@router.get("/domains/{domain_id}/dns-analytics")
def dns_analytics(tenant_id: UUID, domain_id: UUID, limit: int = Query(24, ge=1, le=200), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    try:
        live = summarize_powerdns_zone(PowerDNSClient().get_zone(domain.ascii_name))
    except PowerDNSError as exc:
        raise HTTPException(502, detail=str(exc)) from exc
    history = db.scalars(
        select(DnsZoneAnalyticsSnapshot)
        .where(DnsZoneAnalyticsSnapshot.tenant_id == tenant_id, DnsZoneAnalyticsSnapshot.domain_id == domain.id)
        .order_by(DnsZoneAnalyticsSnapshot.captured_at.desc()).limit(limit)
    ).all()
    return {
        "domain": domain.ascii_name,
        "live": live,
        "history": [
            {
                "captured_at": item.captured_at, "zone_kind": item.zone_kind, "serial": item.serial,
                "dnssec_enabled": item.dnssec_enabled, "rrset_count": item.rrset_count,
                "record_count": item.record_count, "type_counts": json.loads(item.type_counts_json or "{}"),
            }
            for item in history
        ],
    }


@router.post("/domains/{domain_id}/dns-analytics/snapshot", status_code=status.HTTP_201_CREATED)
def snapshot_dns_analytics(tenant_id: UUID, domain_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain = _domain_or_404(db, tenant_id, domain_id)
    try:
        summary = summarize_powerdns_zone(PowerDNSClient().get_zone(domain.ascii_name))
    except PowerDNSError as exc:
        raise HTTPException(502, detail=str(exc)) from exc
    row = DnsZoneAnalyticsSnapshot(
        tenant_id=tenant_id, domain_id=domain.id, zone_kind=summary["zone_kind"], serial=summary["serial"],
        dnssec_enabled=summary["dnssec_enabled"], rrset_count=summary["rrset_count"], record_count=summary["record_count"],
        type_counts_json=json.dumps(summary["type_counts"], sort_keys=True),
    )
    db.add(row)
    _audit(db, tenant_id, current, "edge.dns_analytics.snapshot", domain, {"record_count": summary["record_count"]})
    db.commit()
    db.refresh(row)
    return {"captured_at": row.captured_at, **summary}
