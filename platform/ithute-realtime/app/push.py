import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from .config import get_settings


@dataclass
class CachedToken:
    value: str = ""
    expires_at: float = 0.0


class PushBridge:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.token = CachedToken()

    def _service_token(self) -> str:
        now = time.time()
        if self.token.value and self.token.expires_at - 30 > now:
            return self.token.value
        if not self.settings.platform_client_secret:
            raise RuntimeError("REALTIME_PLATFORM_CLIENT_SECRET is required for Push integration")
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                self.settings.auth_service_token_url,
                json={
                    "client_id": self.settings.platform_client_id,
                    "client_secret": self.settings.platform_client_secret,
                    "audience": "ithute-push",
                    "scope": "push.send.delegated",
                },
            )
            response.raise_for_status()
            payload = response.json()
        self.token = CachedToken(
            value=str(payload["access_token"]),
            expires_at=now + int(payload.get("expires_in", 300)),
        )
        return self.token.value

    def notify_event(
        self,
        *,
        source_client_id: str,
        recipient_sub: uuid.UUID,
        event_id: uuid.UUID,
        event_type: str,
        title: str,
        body: str,
        route: str | None,
        data: dict[str, Any],
        ttl_seconds: int,
        priority: str = "normal",
    ) -> None:
        if not self.settings.push_enabled:
            return
        token = self._service_token()
        payload_data = {str(key): value for key, value in data.items()}
        payload_data.update(
            {
                "type": event_type,
                "event_id": str(event_id),
                "priority": priority,
            }
        )
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{self.settings.push_url.rstrip('/')}/v1/platform/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": f"realtime:{source_client_id}:{event_id}:{recipient_sub}",
                },
                json={
                    "source_client_id": source_client_id,
                    "recipient_sub": str(recipient_sub),
                    "title": title[:160],
                    "body": body[:500],
                    "route": route,
                    "sound": "default",
                    "data": payload_data,
                    "ttl_seconds": max(60, min(ttl_seconds, 604800)),
                },
            )
            response.raise_for_status()

    def notify_chat_message(
        self,
        *,
        source_client_id: str,
        recipient_sub: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        body: str,
    ) -> None:
        self.notify_event(
            source_client_id=source_client_id,
            recipient_sub=recipient_sub,
            event_id=message_id,
            event_type="chat.message",
            title="New message",
            body=body[:240] if body else "You have a new message",
            route=f"/chat/{conversation_id}",
            data={"conversation_id": str(conversation_id), "message_id": str(message_id)},
            ttl_seconds=3600,
        )


push_bridge = PushBridge()
