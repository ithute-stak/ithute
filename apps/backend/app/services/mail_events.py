import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import redis
import redis.asyncio as async_redis

from app.core.config import settings
from app.services.webmail import _imap


logger = logging.getLogger(__name__)


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


STREAM_MAXLEN = _bounded_env_int("WEBMAIL_EVENT_STREAM_MAXLEN", 1000, 100, 10000)
POLL_SECONDS = _bounded_env_int("WEBMAIL_EVENT_POLL_SECONDS", 5, 3, 60)


def _mailbox_hash(address: str) -> str:
    return hashlib.sha256(address.strip().lower().encode("utf-8")).hexdigest()


def stream_key(address: str) -> str:
    return f"webmail:events:{_mailbox_hash(address)}"


def fingerprint_key(address: str) -> str:
    return f"webmail:event-fingerprint:{_mailbox_hash(address)}"


def probe_lock_key(address: str) -> str:
    return f"webmail:event-probe-lock:{_mailbox_hash(address)}"


def _event_fields(event_type: str, data: dict[str, Any] | None = None) -> dict[str, str]:
    return {
        "type": event_type,
        "data": json.dumps(data or {}, separators=(",", ":"), ensure_ascii=False),
        "at": datetime.now(timezone.utc).isoformat(),
    }


def _mailbox_counts(address: str, password: str) -> list[dict[str, Any]]:
    """Minimal IMAP snapshot used by realtime detection; intentionally skips contact discovery."""
    client = _imap(address, password)
    try:
        status, data = client.list()
        if status != "OK":
            return []
        rows: list[dict[str, Any]] = []
        for item in data or []:
            text = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
            name = text.rsplit(" ", 1)[-1].strip('"')
            result_status, result = client.status(name, "(MESSAGES UNSEEN)")
            values = result[0].decode(errors="replace") if result_status == "OK" and result and result[0] else ""
            match = re.search(r"MESSAGES\s+(\d+).*UNSEEN\s+(\d+)", values)
            rows.append(
                {
                    "name": name,
                    "messages": int(match.group(1)) if match else 0,
                    "unseen": int(match.group(2)) if match else 0,
                }
            )
        return rows
    finally:
        try:
            client.logout()
        except Exception:
            pass


def publish_mail_event(address: str, event_type: str, data: dict[str, Any] | None = None) -> str | None:
    """Best-effort event publication. Mail actions must not fail if realtime fanout is unavailable."""
    client: redis.Redis | None = None
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return client.xadd(
            stream_key(address),
            _event_fields(event_type, data),
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
    except redis.RedisError:
        logger.warning("webmail realtime event publication failed", exc_info=True)
        return None
    finally:
        if client is not None:
            try:
                client.close()
            except redis.RedisError:
                pass


class MailEventStream:
    def __init__(self, address: str):
        self.address = address.strip().lower()
        self.client = async_redis.Redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        await self.client.aclose()

    async def read(self, last_id: str = "$", block_ms: int | None = None) -> list[dict[str, Any]]:
        timeout = block_ms if block_ms is not None else POLL_SECONDS * 1000
        rows = await self.client.xread({stream_key(self.address): last_id}, count=50, block=timeout)
        result: list[dict[str, Any]] = []
        for _key, entries in rows:
            for event_id, fields in entries:
                try:
                    data = json.loads(fields.get("data") or "{}")
                except json.JSONDecodeError:
                    data = {}
                result.append(
                    {
                        "id": event_id,
                        "type": fields.get("type") or "mailbox.changed",
                        "at": fields.get("at") or "",
                        "data": data,
                    }
                )
        return result

    async def probe_mailbox(self, password: str) -> dict[str, Any] | None:
        """Detect external IMAP changes; one connection probes each mailbox per poll window."""
        try:
            acquired = await self.client.set(probe_lock_key(self.address), "1", nx=True, ex=POLL_SECONDS)
        except redis.RedisError:
            logger.debug("webmail event probe lock unavailable", exc_info=True)
            return None
        if not acquired:
            return None

        try:
            counts = await asyncio.to_thread(_mailbox_counts, self.address, password)
        except Exception:
            logger.debug("webmail event IMAP probe failed", exc_info=True)
            return None

        snapshot = {"folders": counts}
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        key = fingerprint_key(self.address)
        try:
            previous = await self.client.get(key)
            await self.client.set(key, encoded, ex=86400)
            if previous is not None and previous != encoded:
                event_id = await self.client.xadd(
                    stream_key(self.address),
                    _event_fields("mailbox.changed", snapshot),
                    maxlen=STREAM_MAXLEN,
                    approximate=True,
                )
                return {"id": event_id, "type": "mailbox.changed", "data": snapshot}
        except redis.RedisError:
            logger.debug("webmail event fingerprint update failed", exc_info=True)
        return None
