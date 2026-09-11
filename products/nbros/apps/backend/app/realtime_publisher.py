from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import settings


@dataclass
class _Token:
    value: str
    expires_at: float


class RealtimePublisher:
    def __init__(self) -> None:
        self._token: _Token | None = None

    def _request_json(self, url: str, payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    def _service_token(self) -> str | None:
        if not settings.realtime_publish_enabled or not settings.realtime_service_client_secret:
            return None
        now = time.time()
        if self._token and self._token.expires_at - 30 > now:
            return self._token.value
        result = self._request_json(
            settings.auth_service_token_url,
            {
                "client_id": "nbros",
                "client_secret": settings.realtime_service_client_secret,
                "audience": "ithute-realtime",
                "scope": "realtime.publish",
            },
        )
        value = str(result["access_token"])
        expires_in = max(int(result.get("expires_in", 300)), 60)
        self._token = _Token(value=value, expires_at=now + expires_in)
        return value

    def publish_fleet_alert(
        self,
        *,
        recipient_subs: list[str],
        alert_id: str,
        branch_id: str,
        vehicle_id: str,
        registration_plate: str,
        severity: str,
        label: str,
        detail: str,
        source_type: str,
        source_id: str,
        fingerprint: str,
    ) -> bool:
        if not recipient_subs:
            return False
        token = self._service_token()
        if not token:
            return False
        self._request_json(
            f"{settings.realtime_public_url.rstrip('/')}/v1/platform/events",
            {
                "event_type": "fleet.alert.changed",
                "version": 1,
                "recipient_subs": recipient_subs,
                "title": f"Fleet alert · {registration_plate}",
                "body": f"{label}: {detail}",
                "route": f"/fleet/vehicles/{vehicle_id}?branch={branch_id}",
                "data": {
                    "alert_id": alert_id,
                    "branch_id": branch_id,
                    "vehicle_id": vehicle_id,
                    "registration_plate": registration_plate,
                    "severity": severity,
                    "label": label,
                    "detail": detail,
                    "source_type": source_type,
                    "source_id": source_id,
                },
                "priority": "critical" if severity == "red" else "high",
                "ttl_seconds": 86400,
                "push": severity == "red",
                "broadcast_connected": False,
                "audience_label": "NBros Fleet",
                "idempotency_key": f"fleet-alert:{alert_id}:{fingerprint[:20]}",
            },
            token=token,
        )
        return True


publisher = RealtimePublisher()
