"""Validate OAuth redirect URI registrations before saving trusted client metadata."""
from __future__ import annotations

from urllib.parse import urlsplit


def validate_redirect_uris(values: list[str], *, limit: int = 10) -> tuple[str, ...]:
    if not values or len(values) > limit:
        raise ValueError("Provide between 1 and 10 redirect URLs")
    unique: list[str] = []
    for raw in values:
        if not isinstance(raw, str) or not raw or raw.strip() != raw or len(raw) > 2048:
            raise ValueError("Invalid redirect URL")
        try:
            parts = urlsplit(raw)
            host = parts.hostname
            port = parts.port
        except ValueError as exc:
            raise ValueError("Invalid redirect URL") from exc
        if not host or parts.username is not None or parts.password is not None or parts.fragment:
            raise ValueError("Redirect URL must have a host and no credentials or fragment")
        if any(char in raw for char in ("*", "\\", "\r", "\n")):
            raise ValueError("Redirect URL cannot contain wildcards or control characters")
        is_https = parts.scheme == "https" and bool(host) and port != 0
        is_loopback = parts.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"} and port is not None and port != 0
        if not (is_https or is_loopback):
            raise ValueError("HTTPS required, except explicit localhost development redirect URLs")
        if raw not in unique:
            unique.append(raw)
    return tuple(unique)
