from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.services.caddy_routes import CaddyRouteError, reload_caddy


def mta_sts_policy(domain: str) -> str:
    return (
        "version: STSv1\n"
        f"mode: {settings.mail_mta_sts_mode}\n"
        f"mx: {settings.mail_hostname.rstrip('.')}\n"
        f"max_age: {settings.mail_mta_sts_max_age_seconds}\n"
    )


def render_mta_sts_route(domain: str) -> str:
    hostname = f"mta-sts.{domain.strip().lower().rstrip('.')}"
    policy = mta_sts_policy(domain).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'''{hostname} {{
    header {{
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "no-referrer"
        Cache-Control "public, max-age=300"
        -Server
    }}
    @mta_sts_policy path /.well-known/mta-sts.txt
    respond @mta_sts_policy "{policy}" 200
    respond 404
}}
'''


def _route_path(domain_id: UUID) -> Path:
    routes_dir = Path(os.getenv("CADDY_ROUTES_DIR", "/caddy-routes"))
    routes_dir.mkdir(parents=True, exist_ok=True)
    return routes_dir / f"ithute-mta-sts-{domain_id}.caddy"


def activate_mta_sts_route(domain_id: UUID, domain: str) -> None:
    if not settings.mail_mta_sts_enabled:
        return
    target = _route_path(domain_id)
    previous = target.read_bytes() if target.exists() else None
    content = render_mta_sts_route(domain)
    fd, temp_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        try:
            reload_caddy()
        except Exception as exc:
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(previous)
            try:
                reload_caddy()
            except Exception:
                pass
            raise CaddyRouteError("Unable to activate MTA-STS HTTPS policy route") from exc
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
