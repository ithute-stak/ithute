from __future__ import annotations

import json

import httpx

from .config import Settings


def _fnv1a64(data: bytes) -> int:
    value = 14695981039346656037
    for byte in data:
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def python_analyze(route_key: str, frame: dict, shard_count: int) -> dict:
    raw = json.dumps(frame, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    if len(raw) > 64 * 1024:
        raise ValueError("realtime envelope exceeds 64 KiB")
    if b"\x00" in raw:
        raise ValueError("realtime envelope contains NUL")
    return {
        "scan": {
            "bytes": len(raw),
            "utf8_valid": True,
            "json_object_shape": True,
            "nul_bytes": 0,
            "control_bytes": sum(1 for value in raw if value < 32 and value not in {9, 10, 13}),
        },
        "scan_engine": "python-fallback",
        "shard": _fnv1a64(route_key.encode("utf-8")) % shard_count,
        "shard_engine": "python-fallback",
    }


async def analyze_realtime(
    settings: Settings,
    *,
    route_key: str,
    frame: dict,
) -> dict:
    shard_count = max(1, min(int(settings.route_shard_count), 65536))
    if not settings.native_engine_token:
        return python_analyze(route_key, frame, shard_count)

    try:
        async with httpx.AsyncClient(
            timeout=max(settings.engine_http_timeout_seconds, 2.0),
            trust_env=False,
        ) as client:
            response = await client.post(
                settings.native_engine_url.rstrip("/") + "/v1/realtime/analyze",
                headers={"Authorization": f"Bearer {settings.native_engine_token}"},
                json={
                    "route_key": route_key,
                    "shard_count": shard_count,
                    "frame": frame,
                },
            )
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict):
            raise ValueError("invalid native engine response")
        if body.get("scan_engine") not in {"rust", "python-fallback"}:
            raise ValueError("invalid native scan engine")
        if body.get("shard_engine") not in {"cpp", "python-fallback"}:
            raise ValueError("invalid native shard engine")
        shard = int(body.get("shard"))
        if shard < 0 or shard >= shard_count:
            raise ValueError("invalid native shard result")
        return body
    except (httpx.HTTPError, ValueError, TypeError):
        return python_analyze(route_key, frame, shard_count)
