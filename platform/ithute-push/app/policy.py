from __future__ import annotations

from collections import defaultdict

import httpx

from .config import Settings


DEFAULT_PROVIDER_ORDER = {
    "android": ("ithute", "fcm"),
    "ios": ("apns",),
    "web": ("webpush",),
}


def python_transport_order(platform: str, providers: set[str], *, online: bool = False) -> list[str]:
    if platform not in DEFAULT_PROVIDER_ORDER:
        return []
    order: list[str] = []
    if online:
        order.append("realtime")
    order.extend(provider for provider in DEFAULT_PROVIDER_ORDER[platform] if provider in providers)
    return order


def java_transport_order(
    settings: Settings,
    *,
    platform: str,
    providers: set[str],
    online: bool = False,
) -> tuple[list[str], str]:
    params = {
        "platform": platform,
        "online": str(online).lower(),
        "ithute": str("ithute" in providers).lower(),
        "fcm": str("fcm" in providers).lower(),
        "apns": str("apns" in providers).lower(),
        "webpush": str("webpush" in providers).lower(),
    }
    try:
        with httpx.Client(timeout=settings.engine_http_timeout_seconds, trust_env=False) as client:
            response = client.get(settings.java_worker_url.rstrip("/") + "/v1/push/policy", params=params)
            response.raise_for_status()
            body = response.json()
        transports = body.get("transports") if isinstance(body, dict) else None
        if body.get("engine") != "java" or not isinstance(transports, list):
            raise ValueError("invalid Java push policy response")
        filtered = [str(item) for item in transports if str(item) in providers or str(item) == "realtime"]
        return filtered, "java"
    except (httpx.HTTPError, ValueError, TypeError):
        return python_transport_order(platform, providers, online=online), "python-fallback"


def rank_device_endpoints(settings: Settings, endpoints: list) -> list[tuple[object, int]]:
    by_device: dict[str, list] = defaultdict(list)
    for endpoint in endpoints:
        by_device[str(endpoint.device_key)].append(endpoint)

    ranked: list[tuple[object, int]] = []
    for rows in by_device.values():
        platform = str(rows[0].platform)
        by_provider = {str(item.provider): item for item in rows}
        order, _engine = java_transport_order(
            settings,
            platform=platform,
            providers=set(by_provider),
            online=False,
        )
        rank = 0
        for provider in order:
            endpoint = by_provider.get(provider)
            if endpoint is None:
                continue
            ranked.append((endpoint, rank))
            rank += 1
        for provider, endpoint in by_provider.items():
            if provider not in order:
                ranked.append((endpoint, rank))
                rank += 1
    return ranked
