import asyncio
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import WebSocket

from .config import get_settings


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
        return bool(await self._remote_presence(application_id, sub))

    async def presence(self, application_id: str, sub: str) -> dict:
        rows = await self._remote_presence(application_id, sub)
        raw_last = await self.redis.get(self._last_seen_key(application_id, sub))
        return {
            "online": bool(rows),
            "connection_count": len(rows),
            "device_keys": sorted({str(item.get("device_key") or "") for item in rows if item.get("device_key")}),
            "last_seen_at": raw_last,
        }

    async def publish(self, application_id: str, event: dict) -> None:
        await self.redis.publish(
            f"ithute:realtime:events:{application_id}",
            json.dumps(event, separators=(",", ":"), default=str),
        )
        await self.redis.hincrby("ithute:realtime:metrics", "events_published", 1)

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
