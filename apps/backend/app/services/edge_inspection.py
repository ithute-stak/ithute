from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit


class EdgeInspectionError(ValueError):
    pass


def _public_addresses(hostname: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise EdgeInspectionError(f"Origin hostname could not be resolved: {exc}") from exc

    addresses: list[str] = []
    for info in infos:
        raw = info[4][0]
        try:
            parsed = ipaddress.ip_address(raw)
        except ValueError:
            continue
        # Health probes are an outbound platform capability. Never allow them to
        # become an SSRF path into localhost, Docker networks, RFC1918 ranges,
        # link-local ranges or other non-public infrastructure.
        if not parsed.is_global:
            raise EdgeInspectionError("Origin resolves to a non-public IP address; private/internal targets are not allowed")
        value = parsed.compressed
        if value not in addresses:
            addresses.append(value)
    if not addresses:
        raise EdgeInspectionError("Origin has no globally routable IP address")
    return addresses


def _certificate_issuer(cert: dict) -> str | None:
    parts: list[str] = []
    for group in cert.get("issuer", ()):  # CPython ssl certificate tuple format
        for key, value in group:
            parts.append(f"{key}={value}")
    return ", ".join(parts) or None


def _certificate_expiry(cert: dict) -> tuple[datetime | None, int | None]:
    value = cert.get("notAfter")
    if not value:
        return None, None
    try:
        timestamp = ssl.cert_time_to_seconds(value)
    except (ValueError, TypeError, OverflowError):
        return None, None
    expiry = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return expiry, int((expiry - datetime.now(timezone.utc)).total_seconds() // 86400)


def _read_status(sock: socket.socket, limit: int = 16384) -> int | None:
    data = b""
    while b"\r\n" not in data and len(data) < limit:
        chunk = sock.recv(2048)
        if not chunk:
            break
        data += chunk
    first = data.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
    parts = first.split()
    if len(parts) >= 2 and parts[0].startswith("HTTP/"):
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


def inspect_public_origin(url: str, health_path: str = "/", expected_status: int = 200, timeout_seconds: int = 5) -> dict:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise EdgeInspectionError("Origin URL must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise EdgeInspectionError("Origin URL must contain a hostname and must not contain credentials")
    if parsed.fragment:
        raise EdgeInspectionError("Origin URL fragments are not supported")
    if not 100 <= expected_status <= 599:
        raise EdgeInspectionError("Expected HTTP status must be between 100 and 599")
    if not 1 <= timeout_seconds <= 30:
        raise EdgeInspectionError("Probe timeout must be between 1 and 30 seconds")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise EdgeInspectionError("Origin URL contains an invalid port") from exc
    if not 1 <= port <= 65535:
        raise EdgeInspectionError("Origin port is invalid")

    hostname = parsed.hostname.rstrip(".").lower()
    addresses = _public_addresses(hostname, port)
    target_ip = addresses[0]
    base_path = parsed.path if parsed.path and parsed.path != "/" else ""
    probe_path = health_path.strip() or "/"
    if not probe_path.startswith("/"):
        probe_path = "/" + probe_path
    path = (base_path.rstrip("/") + probe_path) or "/"
    if parsed.query:
        path += "?" + parsed.query

    started = time.perf_counter()
    tls_version = None
    cipher = None
    issuer = None
    cert_not_after = None
    cert_days_remaining = None
    status_code = None
    error = None

    raw_socket: socket.socket | None = None
    stream: socket.socket | None = None
    try:
        raw_socket = socket.create_connection((target_ip, port), timeout=timeout_seconds)
        raw_socket.settimeout(timeout_seconds)
        if parsed.scheme == "https":
            context = ssl.create_default_context()
            stream = context.wrap_socket(raw_socket, server_hostname=hostname)
            raw_socket = None
            tls_version = stream.version()
            selected = stream.cipher()
            cipher = selected[0] if selected else None
            cert = stream.getpeercert()
            issuer = _certificate_issuer(cert)
            cert_not_after, cert_days_remaining = _certificate_expiry(cert)
        else:
            stream = raw_socket
            raw_socket = None

        host_header = hostname
        default_port = 443 if parsed.scheme == "https" else 80
        if port != default_port:
            host_header = f"{hostname}:{port}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "User-Agent: Ithute-Edge-Health/1.0\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii", errors="strict")
        stream.sendall(request)
        status_code = _read_status(stream)
        if status_code is None:
            error = "Origin did not return a valid HTTP status line"
    except (OSError, ssl.SSLError, UnicodeError) as exc:
        error = f"{exc.__class__.__name__}: {str(exc)[:300]}"
    finally:
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
        if raw_socket is not None:
            try:
                raw_socket.close()
            except OSError:
                pass

    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
    healthy = error is None and status_code == expected_status
    return {
        "healthy": healthy,
        "resolved_ip": target_ip,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "tls_version": tls_version,
        "cipher": cipher,
        "certificate_issuer": issuer,
        "certificate_not_after": cert_not_after,
        "certificate_days_remaining": cert_days_remaining,
        "error": error,
    }


def summarize_powerdns_zone(zone: dict) -> dict:
    rrsets = zone.get("rrsets") if isinstance(zone, dict) else None
    rrsets = rrsets if isinstance(rrsets, list) else []
    type_counts: dict[str, int] = {}
    record_count = 0
    for rrset in rrsets:
        if not isinstance(rrset, dict):
            continue
        rtype = str(rrset.get("type") or "UNKNOWN").upper()
        records = rrset.get("records") if isinstance(rrset.get("records"), list) else []
        count = len(records)
        type_counts[rtype] = type_counts.get(rtype, 0) + count
        record_count += count
    return {
        "zone_kind": zone.get("kind") if isinstance(zone, dict) else None,
        "serial": zone.get("serial") if isinstance(zone, dict) else None,
        "dnssec_enabled": bool(zone.get("dnssec")) if isinstance(zone, dict) else False,
        "rrset_count": len(rrsets),
        "record_count": record_count,
        "type_counts": dict(sorted(type_counts.items())),
    }
