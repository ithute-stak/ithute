from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class SecretProviderError(RuntimeError):
    pass


@dataclass
class _Cached:
    value: str
    expires_at: float


_CACHE: dict[str, _Cached] = {}
_LOCK = threading.Lock()


def _cache_seconds() -> int:
    try:
        return max(5, min(int(os.getenv("ITHUTE_SECRET_CACHE_SECONDS", "60")), 3600))
    except ValueError:
        return 60


def _from_file(reference: str) -> str:
    path = reference.removeprefix("file://")
    if not path.startswith("/"):
        raise SecretProviderError("Secret file reference must be absolute")
    if os.getenv("ENVIRONMENT", "development").lower() == "production" and not path.startswith("/run/secrets/"):
        raise SecretProviderError("Production secret files must live under /run/secrets")
    try:
        value = open(path, "r", encoding="utf-8").read().strip()
    except OSError as exc:
        raise SecretProviderError("Secret file is unavailable") from exc
    if not value:
        raise SecretProviderError("Secret file is empty")
    return value


def _vault_token() -> str:
    token_file = os.getenv("ITHUTE_VAULT_TOKEN_FILE", "/run/secrets/vault-token")
    try:
        token = open(token_file, "r", encoding="utf-8").read().strip()
    except OSError as exc:
        raise SecretProviderError("Vault token file is unavailable") from exc
    if not token:
        raise SecretProviderError("Vault token is empty")
    return token


def _from_vault(reference: str) -> str:
    raw = reference.removeprefix("vault://")
    path, sep, field = raw.partition("#")
    if not sep or not path or not field or "/" not in path:
        raise SecretProviderError("Vault references must use vault://mount/path#field")
    mount, secret_path = path.split("/", 1)
    addr = os.getenv("ITHUTE_VAULT_ADDR", "").strip().rstrip("/")
    if not addr.startswith(("https://", "http://vault:", "http://vault/")):
        raise SecretProviderError("ITHUTE_VAULT_ADDR must use HTTPS or the private vault service")
    url = f"{addr}/v1/{mount}/data/{secret_path}"
    headers = {"X-Vault-Token": _vault_token(), "Accept": "application/json"}
    namespace = os.getenv("ITHUTE_VAULT_NAMESPACE", "").strip()
    if namespace:
        headers["X-Vault-Namespace"] = namespace
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SecretProviderError("Vault secret lookup failed") from exc
    data = payload.get("data", {}).get("data", {})
    value = data.get(field) if isinstance(data, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise SecretProviderError("Vault secret field is missing or empty")
    return value.strip()


def resolve_secret(reference: str | None, fallback: str | None, *, name: str) -> str:
    ref = (reference or "").strip()
    if not ref:
        value = (fallback or "").strip()
        if not value:
            raise SecretProviderError(f"{name} is not configured")
        return value

    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(ref)
        if cached and cached.expires_at > now:
            return cached.value

    if ref.startswith("file://"):
        value = _from_file(ref)
    elif ref.startswith("vault://"):
        value = _from_vault(ref)
    else:
        raise SecretProviderError("Unsupported secret reference scheme")

    with _LOCK:
        _CACHE[ref] = _Cached(value=value, expires_at=now + _cache_seconds())
    return value


def clear_secret_cache(reference: str | None = None) -> None:
    with _LOCK:
        if reference:
            _CACHE.pop(reference, None)
        else:
            _CACHE.clear()
