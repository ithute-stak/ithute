import asyncio
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import redis.asyncio as redis
from fastapi import WebSocket

from .config import get_settings
from .native_engine import analyze_realtime


class ConnectionLimitError(RuntimeError):
    pass


@dataclass
class ConnectionRecord:
    websocket: WebSocket
    device_key: str
    connected_at: str


class RealtimeHub:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = redis.from_url(self.settings.redis_url, decode_responses=True)
        self.connections: dict[tuple[str, str], dict[str, ConnectionRecord]] = defaultdict(dict)
        self.listener_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self.listener_task is None:
            self.listener_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
            self.listener_task = None
        await self.redis.aclose()

    def _presence_key(self, application_id: str, sub: str, connection_id: str) -> str:
        return f"ithute:realtime:presence:{application_id}:{sub}:{connection_id}"

    def _last_seen_key(self, application_id: str, sub: str) -> str:
        return f"ithute:realtime:lastseen:{application_id}:{sub}"


    def _go_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.go_gateway_token}"}

    async def _go_presence(self, application_id: str, sub: str) -> dict:
        if not self.settings.go_gateway_token:
            return {"online": False, "connection_count": 0}
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.engine_http_timeout_seconds,
                trust_env=False,
            ) as client:
                response = await client.get(
                    self.settings.go_worker_url.rstrip("/") + "/v1/realtime/presence",
                    headers=self._go_headers(),
                    params={"application_id": application_id, "sub": sub},
                )
                response.raise_for_status()
                body = response.json()
            if not isinstance(body, dict) or body.get("engine") != "go":
                raise ValueError("invalid Go realtime presence response")
            return {
                "online": bool(body.get("online")),
                "connection_count": max(0, int(body.get("connection_count") or 0)),
            }
        except (httpx.HTTPError, ValueError, TypeError):
            return {"online": False, "connection_count": 0}

    async def _publish_go(self, application_id: str, event: dict) -> int:
        if not self.settings.go_gateway_token:
            return 0
        recipients = [str(value) for value in event.get("recipients", [])]
        route_key = application_id + ":" + (
            "broadcast" if event.get("broadcast_connected") else ",".join(sorted(recipients))
        )
        analysis = await analyze_realtime(
            self.settings,
            route_key=route_key,
            frame=event,
        )
        payload = {
            "application_id": application_id,
            "recipients": recipients,
            "broadcast_connected": bool(event.get("broadcast_connected")),
            "routing_shard": int(analysis["shard"]),
            "event": event,
        }
        try:
            async with httpx.AsyncClient(
                timeout=max(self.settings.engine_http_timeout_seconds, 2.0),
                trust_env=False,
            ) as client:
                response = await client.post(
                    self.settings.go_worker_url.rstrip("/") + "/v1/realtime/publish",
                    headers=self._go_headers(),
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
            if not isinstance(body, dict) or body.get("engine") != "go":
                raise ValueError("invalid Go realtime publish response")
            return max(0, int(body.get("delivered") or 0))
        except (httpx.HTTPError, ValueError, TypeError):
            return 0

    async def _remote_presence(self, application_id: str, sub: str) -> list[dict]:
        rows: list[dict] = []
        pattern = f"ithute:realtime:presence:{application_id}:{sub}:*"
        async for key in self.redis.scan_iter(match=pattern, count=50):
            raw = await self.redis.get(key)
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        return rows

    async def connect(self, application_id: str, sub: str, websocket: WebSocket, device_key: str) -> str:
        existing = await self._remote_presence(application_id, sub)
        if len(existing) >= self.settings.max_connections_per_user:
            raise ConnectionLimitError("maximum concurrent connections reached")
        same_device = sum(1 for item in existing if item.get("device_key") == device_key)
        if same_device >= self.settings.max_connections_per_device:
            raise ConnectionLimitError("maximum device connections reached")
        connection_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.connections[(application_id, sub)][connection_id] = ConnectionRecord(websocket, device_key, now)
        await self.refresh_presence(application_id, sub, connection_id)
        await self.redis.hincrby("ithute:realtime:metrics", "connections_opened", 1)
        return connection_id

    async def refresh_presence(self, application_id: str, sub: str, connection_id: str) -> None:
        record = self.connections.get((application_id, sub), {}).get(connection_id)
        if record is None:
            return
        payload = {"device_key": record.device_key, "connected_at": record.connected_at, "state": "online"}
        await self.redis.set(
            self._presence_key(application_id, sub, connection_id),
            json.dumps(payload, separators=(",", ":")),
            ex=self.settings.websocket_presence_ttl_seconds,
        )

    async def disconnect(self, application_id: str, sub: str, connection_id: str) -> None:
        bucket = self.connections.get((application_id, sub))
        if bucket:
            bucket.pop(connection_id, None)
            if not bucket:
                self.connections.pop((application_id, sub), None)
        await self.redis.delete(self._presence_key(application_id, sub, connection_id))
        await self.redis.set(self._last_seen_key(application_id, sub), datetime.now(timezone.utc).isoformat(), ex=2592000)
        await self.redis.hincrby("ithute:realtime:metrics", "connections_closed", 1)

    async def is_online(self, application_id: str, sub: str) -> bool:
        if await self._remote_presence(application_id, sub):
            return True
        return bool((await self._go_presence(application_id, sub))["online"])

    async def presence(self, application_id: str, sub: str) -> dict:
        rows = await self._remote_presence(application_id, sub)
        go = await self._go_presence(application_id, sub)
        raw_last = await self.redis.get(self._last_seen_key(application_id, sub))
        return {
            "online": bool(rows) or bool(go["online"]),
            "connection_count": len(rows) + int(go["connection_count"]),
            "device_keys": sorted({str(item.get("device_key") or "") for item in rows if item.get("device_key")}),
            "last_seen_at": raw_last,
            "go_connections": int(go["connection_count"]),
        }

    async def publish(self, application_id: str, event: dict) -> None:
        go_delivered, _ = await asyncio.gather(
            self._publish_go(application_id, event),
            self.redis.publish(
                f"ithute:realtime:events:{application_id}",
                json.dumps(event, separators=(",", ":"), default=str),
            ),
            return_exceptions=False,
        )
        await self.redis.hincrby("ithute:realtime:metrics", "events_published", 1)
        if go_delivered:
            await self.redis.hincrby("ithute:realtime:metrics", "go_frames_delivered", int(go_delivered))

    async def metrics(self) -> dict[str, int]:
        raw = await self.redis.hgetall("ithute:realtime:metrics")
        result = {key: int(value) for key, value in raw.items()}
        result["local_connections"] = sum(len(bucket) for bucket in self.connections.values())
        return result

    async def _send(self, application_id: str, recipient: str, connection_id: str, record: ConnectionRecord, payload: str) -> None:
        try:
            await asyncio.wait_for(record.websocket.send_text(payload), timeout=self.settings.websocket_send_timeout_seconds)
            await self.redis.hincrby("ithute:realtime:metrics", "frames_delivered", 1)
        except Exception:
            await self.redis.hincrby("ithute:realtime:metrics", "slow_or_failed_clients", 1)
            await self.disconnect(application_id, recipient, connection_id)

    async def _listen(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.psubscribe("ithute:realtime:events:*")
        try:
            async for item in pubsub.listen():
                if item.get("type") != "pmessage":
                    continue
                try:
                    event = json.loads(item["data"])
                    application_id = str(event.get("application_id") or "")
                    recipients = {str(value) for value in event.get("recipients", [])}
                    broadcast_connected = bool(event.get("broadcast_connected"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if not application_id:
                    continue
                payload = json.dumps(event, separators=(",", ":"), default=str)
                targets: list[tuple[str, str, ConnectionRecord]] = []
                if broadcast_connected:
                    for (app_id, sub), bucket in list(self.connections.items()):
                        if app_id != application_id:
                            continue
                        for connection_id, record in list(bucket.items()):
                            targets.append((sub, connection_id, record))
                else:
                    for recipient in recipients:
                        for connection_id, record in list(self.connections.get((application_id, recipient), {}).items()):
                            targets.append((recipient, connection_id, record))
                await asyncio.gather(
                    *(self._send(application_id, recipient, connection_id, record, payload)
                      for recipient, connection_id, record in targets),
                    return_exceptions=True,
                )
        finally:
            await pubsub.aclose()


hub = RealtimeHub()
