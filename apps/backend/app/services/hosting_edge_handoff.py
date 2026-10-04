from __future__ import annotations

import ipaddress
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EdgeApplication, EdgeInspection, EdgeOrigin, EdgeRouteDeployment, HostingProject
from app.services.caddy_routes import CaddyRouteError, activate_route, propagation_state


class HostingOriginError(RuntimeError):
    pass


def _allowed_origin_networks() -> list[ipaddress._BaseNetwork]:
    raw = os.getenv("ITHUTE_HOSTING_ORIGIN_CIDRS", "").strip()
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        values = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"]
    networks = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError as exc:
            raise HostingOriginError(f"Invalid ITHUTE_HOSTING_ORIGIN_CIDRS entry: {value}") from exc
    return networks


def validate_trusted_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise HostingOriginError("Hosting origin must be a credential-free HTTP URL")
    if parsed.path not in {"", "/"}:
        raise HostingOriginError("Hosting origin must not contain a path")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise HostingOriginError("Hosting origin must use a literal private/VPN IP address") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise HostingOriginError("Hosting origin must use a private/VPN IPv4 address")
    if not any(address in network for network in _allowed_origin_networks() if network.version == 4):
        raise HostingOriginError("Hosting origin IP is outside the configured trusted origin networks")
    try:
        port = parsed.port
    except ValueError as exc:
        raise HostingOriginError("Hosting origin port is invalid") from exc
    if port is None or not 1024 <= port <= 65535:
        raise HostingOriginError("Hosting origin requires an explicit non-privileged TCP port")
    return f"http://{address}:{port}"


def inspect_trusted_origin(origin_url: str, health_path: str, expected_status: int = 200, timeout_seconds: int = 5) -> dict:
    origin = validate_trusted_origin(origin_url)
    path = health_path.strip() or "/"
    if not path.startswith("/") or "\r" in path or "\n" in path:
        raise HostingOriginError("Invalid hosting origin health path")
    url = origin + path
    started = datetime.now(timezone.utc)
    try:
        response = httpx.get(url, timeout=timeout_seconds, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise HostingOriginError(f"Trusted hosting origin is unreachable: {exc.__class__.__name__}") from exc
    elapsed = max(0, int((datetime.now(timezone.utc) - started).total_seconds() * 1000))
    healthy = response.status_code == expected_status or (expected_status == 200 and 200 <= response.status_code < 400)
    return {
        "healthy": healthy,
        "status_code": response.status_code,
        "latency_ms": elapsed,
        "error": None if healthy else f"Origin returned HTTP {response.status_code}",
    }


def reconcile_project_edge(db: Session, project: HostingProject, origin_url: str) -> dict:
    if not project.hostname or not project.domain_id:
        return {"status": "not_requested", "hostname": project.hostname}
    origin_url = validate_trusted_origin(origin_url)
    app = db.scalar(select(EdgeApplication).where(
        EdgeApplication.tenant_id == project.tenant_id,
        EdgeApplication.hostname == project.hostname,
    ))
    if app is None:
        return {"status": "pending_edge_application", "hostname": project.hostname}
    if not app.enabled or app.mode != "protected":
        return {"status": "pending_mode", "hostname": app.hostname, "application_id": str(app.id)}

    origin = db.scalar(select(EdgeOrigin).where(
        EdgeOrigin.application_id == app.id,
        EdgeOrigin.name == "ithute-hosting",
    ))
    if origin is None:
        origin = EdgeOrigin(
            application_id=app.id,
            name="ithute-hosting",
            url=origin_url,
            enabled=True,
            weight=100,
            failover_priority=1,
            health_path=project.health_path,
            expected_status=200,
            timeout_seconds=5,
        )
        db.add(origin)
        db.flush()
    else:
        origin.url = origin_url
        origin.enabled = True
        origin.health_path = project.health_path
        origin.expected_status = 200

    route = db.scalar(select(EdgeRouteDeployment).where(EdgeRouteDeployment.application_id == app.id))
    if route is None:
        route = EdgeRouteDeployment(application_id=app.id)
        db.add(route)
        db.flush()

    route.last_checked_at = datetime.now(timezone.utc)
    route.error = None

    try:
        propagation = propagation_state(app.hostname)
    except CaddyRouteError as exc:
        route.status = "error"
        route.error = str(exc)
        return {"status": route.status, "hostname": app.hostname, "application_id": str(app.id), "error": route.error}

    route.expected_ips_json = json.dumps(propagation["expected_ips"])
    route.observed_ips_json = json.dumps(propagation["observed_ips"])
    if not propagation["propagated"]:
        route.status = "pending_dns"
        route.error = "DNS has not propagated to an Ithute edge IP yet."
        return {"status": route.status, "hostname": app.hostname, "application_id": str(app.id), "expected_ips": propagation["expected_ips"], "observed_ips": propagation["observed_ips"]}

    try:
        observed = inspect_trusted_origin(origin.url, origin.health_path, origin.expected_status, origin.timeout_seconds)
    except HostingOriginError as exc:
        route.status = "pending_origin"
        route.error = str(exc)
        return {"status": route.status, "hostname": app.hostname, "application_id": str(app.id), "error": route.error}

    db.add(EdgeInspection(
        application_id=app.id,
        origin_id=origin.id,
        healthy=observed["healthy"],
        status_code=observed["status_code"],
        latency_ms=observed["latency_ms"],
        error=observed["error"],
    ))
    if not observed["healthy"]:
        route.status = "pending_origin"
        route.error = observed["error"]
        return {"status": route.status, "hostname": app.hostname, "application_id": str(app.id), "error": route.error}

    try:
        activate_route(str(app.id), app.hostname, origin.url)
    except CaddyRouteError as exc:
        route.status = "error"
        route.error = str(exc)
        return {"status": route.status, "hostname": app.hostname, "application_id": str(app.id), "error": route.error}

    route.caddy_revision += 1
    route.activated_at = datetime.now(timezone.utc)

    # Caddy has the route now, but certificate issuance can be asynchronous.
    try:
        response = httpx.get(f"https://{app.hostname}{project.health_path}", timeout=8, follow_redirects=False)
        if 200 <= response.status_code < 400:
            route.status = "active"
            route.error = None
        else:
            route.status = "pending_tls"
            route.error = f"Public HTTPS route returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        route.status = "pending_tls"
        route.error = f"Waiting for HTTPS/TLS readiness: {exc.__class__.__name__}"

    return {
        "status": route.status,
        "hostname": app.hostname,
        "application_id": str(app.id),
        "origin_url": origin.url,
        "error": route.error,
    }
