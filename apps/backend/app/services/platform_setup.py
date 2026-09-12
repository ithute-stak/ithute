from __future__ import annotations

import ipaddress
import os
import re
import tempfile
from dataclasses import dataclass

import dns.resolver
import httpx

from app.core.config import settings


_DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")


class PlatformSetupError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlatformNames:
    domain: str
    panel: str
    api: str
    groupware: str
    mail: str
    ns1: str
    ns2: str


def normalize_platform_domain(value: str) -> str:
    raw = value.strip().rstrip(".")
    if not raw:
        raise ValueError("Primary domain is required")
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        pass
    else:
        raise ValueError("Primary domain must be a DNS name, not an IP address")
    try:
        ascii_name = raw.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Primary domain contains invalid characters") from exc
    if len(ascii_name) > 253 or not _DOMAIN_RE.fullmatch(ascii_name):
        raise ValueError("Primary domain must be a valid fully-qualified DNS name")
    if any(label.startswith("xn--") and len(label) < 5 for label in ascii_name.split(".")):
        raise ValueError("Primary domain contains an invalid IDN label")
    return ascii_name


def platform_names(domain: str) -> PlatformNames:
    domain = normalize_platform_domain(domain)
    return PlatformNames(
        domain=domain,
        # Keep the legacy `panel` field for database/config compatibility, but
        # the public frontend now lives at the platform apex. There is no
        # separate panel.<domain> application hostname.
        panel=domain,
        api=f"api.{domain}",
        groupware=f"groupware.{domain}",
        mail=f"mail.{domain}",
        ns1=f"ns1.{domain}",
        ns2=f"ns2.{domain}",
    )


def validate_public_ip(value: str, field: str = "IP address") -> str:
    try:
        parsed = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid IP address") from exc
    if not parsed.is_global:
        raise ValueError(f"{field} must be a globally routable public IP address")
    return str(parsed)


def _resolve(resolver: dns.resolver.Resolver, name: str, rtype: str) -> list[str]:
    answers = resolver.resolve(name, rtype, lifetime=4)
    if rtype == "NS":
        return sorted(str(item.target).rstrip(".").lower() for item in answers)
    return sorted(str(item).rstrip(".") for item in answers)


def verify_public_delegation(names: PlatformNames, ns1_ip: str, ns2_ip: str) -> dict:
    resolver = dns.resolver.Resolver(configure=True)
    expected_ns = sorted([names.ns1, names.ns2])
    checks: dict[str, dict] = {}

    def check(name: str, rtype: str, expected: list[str]) -> None:
        try:
            actual = _resolve(resolver, name, rtype)
            ok = all(item in actual for item in expected)
            checks[f"{name}:{rtype}"] = {"ok": ok, "expected": expected, "actual": actual}
        except Exception as exc:  # DNS failures are returned as state, not server errors.
            checks[f"{name}:{rtype}"] = {"ok": False, "expected": expected, "actual": [], "detail": exc.__class__.__name__}

    check(names.domain, "NS", expected_ns)
    check(names.ns1, "A", [ns1_ip])
    check(names.ns2, "A", [ns2_ip])
    check(names.panel, "A", [ns1_ip])
    check(names.api, "A", [ns1_ip])
    check(names.mail, "A", [ns1_ip])
    check(names.groupware, "A", [ns1_ip])

    required_keys = [
        f"{names.domain}:NS",
        f"{names.ns1}:A",
        f"{names.ns2}:A",
        f"{names.panel}:A",
        f"{names.api}:A",
        f"{names.mail}:A",
        f"{names.groupware}:A",
    ]
    return {"verified": all(checks[key]["ok"] for key in required_keys), "checks": checks}


def bootstrap_caddyfile(public_ip: str) -> str:
    public_ip = validate_public_ip(public_ip, "Bootstrap public IP")
    return f'''{{
    admin 0.0.0.0:2019
}}

http://{public_ip} {{
    encode zstd gzip
    header {{
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server
    }}

    @api path /api/*
    handle @api {{
        reverse_proxy backend:8000
    }}

    handle {{
        reverse_proxy frontend:3000
    }}
}}
'''


def hardened_caddyfile(names: PlatformNames, public_ip: str, acme_email: str) -> str:
    public_ip = validate_public_ip(public_ip, "Bootstrap public IP")
    email = acme_email.strip()
    if "@" not in email or len(email) > 320:
        raise ValueError("A valid ACME email address is required")
    common = '''        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server'''
    return f'''{{
    email {email}
    admin 0.0.0.0:2019
}}

http://{public_ip} {{
    redir https://{names.panel}{{uri}} permanent
}}

{names.panel} {{
    encode zstd gzip
    header {{
{common}
    }}
    @api path /api/*
    handle @api {{
        reverse_proxy backend:8000
    }}
    handle {{
        reverse_proxy frontend:3000
    }}
}}

{names.api} {{
    encode zstd gzip
    header {{
{common}
    }}
    reverse_proxy backend:8000
}}

{names.groupware} {{
    encode zstd gzip
    header {{
{common}
    }}
    reverse_proxy radicale:5232
}}
'''


def _load_caddy(caddyfile: str) -> None:
    base = settings.caddy_admin_url.rstrip("/")
    try:
        adapted = httpx.post(
            f"{base}/adapt?adapter=caddyfile",
            content=caddyfile.encode(),
            headers={"Content-Type": "text/caddyfile"},
            timeout=10,
        )
        adapted.raise_for_status()
        config = adapted.json()
        loaded = httpx.post(f"{base}/load", json=config, timeout=15)
        loaded.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        raise PlatformSetupError(f"Caddy reload failed: {exc.__class__.__name__}") from exc


def activate_caddy(names: PlatformNames, public_ip: str, acme_email: str) -> None:
    target = settings.caddy_runtime_file
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    new_config = hardened_caddyfile(names, public_ip, acme_email)
    previous: bytes | None = None
    if os.path.exists(target):
        with open(target, "rb") as handle:
            previous = handle.read()

    fd, temp_path = tempfile.mkstemp(prefix="Caddyfile.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_config)
        os.replace(temp_path, target)
        try:
            _load_caddy(new_config)
        except PlatformSetupError:
            if previous is not None:
                with open(target, "wb") as handle:
                    handle.write(previous)
                try:
                    _load_caddy(previous.decode("utf-8"))
                except Exception:
                    pass
            raise
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)