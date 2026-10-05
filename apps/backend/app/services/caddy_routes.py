from __future__ import annotations

import ipaddress
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import dns.resolver
import httpx


_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9]?))*$")


class CaddyRouteError(RuntimeError):
    pass


def _hostname(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if len(value) > 253 or not _HOST_RE.fullmatch(value):
        raise CaddyRouteError("Invalid route hostname")
    return value


def _origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise CaddyRouteError("Origin must be a credential-free HTTP(S) URL")
    if parsed.query or parsed.path not in {"", "/"}:
        raise CaddyRouteError("Origin must not contain a path or query string")
    try:
        port = parsed.port
    except ValueError as exc:
        raise CaddyRouteError("Origin port is invalid") from exc
    if port is not None and not 1 <= port <= 65535:
        raise CaddyRouteError("Origin port is invalid")
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local:
            raise CaddyRouteError("Unsafe origin address")
    default_port = 443 if parsed.scheme == "https" else 80
    return f"{parsed.scheme}://{host}:{port or default_port}"


def expected_edge_ips() -> set[str]:
    configured = os.getenv("ITHUTE_EDGE_PUBLIC_IPS", "").strip()
    values = [item.strip() for item in configured.split(",") if item.strip()]
    bootstrap_public_ip = os.getenv("BOOTSTRAP_PUBLIC_IP", "").strip()
    if not values and bootstrap_public_ip:
        values = [bootstrap_public_ip]
    result: set[str] = set()
    for value in values:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise CaddyRouteError("ITHUTE_EDGE_PUBLIC_IPS contains an invalid address") from exc
        if os.getenv("ENVIRONMENT", "development").lower() == "production" and not address.is_global:
            raise CaddyRouteError("Production edge IPs must be globally routable")
        result.add(str(address))
    if not result:
        raise CaddyRouteError("No edge public IP is configured")
    return result


def resolve_hostname_ips(hostname: str) -> set[str]:
    hostname = _hostname(hostname)
    resolver = dns.resolver.Resolver(configure=True)
    result: set[str] = set()
    for record_type in ("A", "AAAA"):
        try:
            answers = resolver.resolve(hostname, record_type, lifetime=4)
        except Exception:
            continue
        for answer in answers:
            try:
                result.add(str(ipaddress.ip_address(str(answer).rstrip("."))))
            except ValueError:
                continue
    return result


def propagation_state(hostname: str) -> dict:
    expected = expected_edge_ips()
    observed = resolve_hostname_ips(hostname)
    return {
        "propagated": bool(expected.intersection(observed)),
        "expected_ips": sorted(expected),
        "observed_ips": sorted(observed),
    }


def render_route(hostname: str, origin: str) -> str:
    hostname = _hostname(hostname)
    origin = _origin(origin)
    return f'''{hostname} {{
    encode zstd gzip
    header {{
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }}
    reverse_proxy {origin}
}}
'''


def _base_caddyfile() -> str:
    path = Path(os.getenv("CADDY_BASE_FILE", "/caddy-base/Caddyfile"))
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CaddyRouteError("Caddy base configuration is unavailable") from exc


def reload_caddy() -> None:
    base = os.getenv("CADDY_ADMIN_URL", "http://caddy:2019").rstrip("/")
    content = _base_caddyfile()
    try:
        adapted = httpx.post(
            f"{base}/adapt?adapter=caddyfile",
            content=content.encode(),
            headers={"Content-Type": "text/caddyfile"},
            timeout=10,
        )
        adapted.raise_for_status()
        loaded = httpx.post(f"{base}/load", json=adapted.json(), timeout=20)
        loaded.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        raise CaddyRouteError(f"Caddy reload failed: {exc.__class__.__name__}") from exc


def route_path(application_id: str) -> Path:
    routes_dir = Path(os.getenv("CADDY_ROUTES_DIR", "/caddy-routes"))
    routes_dir.mkdir(parents=True, exist_ok=True)
    return routes_dir / f"ithute-edge-{application_id}.caddy"


def activate_route(application_id: str, hostname: str, origin: str) -> None:
    target = route_path(application_id)
    previous = target.read_bytes() if target.exists() else None
    content = render_route(hostname, origin)
    fd, temp_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        try:
            reload_caddy()
        except Exception:
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(previous)
            try:
                reload_caddy()
            except Exception:
                pass
            raise
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def deactivate_route(application_id: str) -> None:
    target = route_path(application_id)
    previous = target.read_bytes() if target.exists() else None
    target.unlink(missing_ok=True)
    try:
        reload_caddy()
    except Exception:
        if previous is not None:
            target.write_bytes(previous)
            try:
                reload_caddy()
            except Exception:
                pass
        raise
