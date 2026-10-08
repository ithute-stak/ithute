"""Account-scoped mailbox change notifications.

Redis Streams retain a bounded replay window unlike ephemeral Pub/Sub.
Only authoritative server-side callers may publish; consumers must derive
the mailbox address from an authenticated session, never user input.
"""
import json
import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)
_ALLOWED = frozenset({"changed", "flags_changed", "message_moved", "message_deleted", "message_received"})
_MAX_REPLAY = 200


def _key(address: str) -> str:
    normalized = address.strip().casefold()
    if not normalized or "@" not in normalized or len(normalized) > 320:
        raise ValueError("Invalid mailbox address")
    # Hashed key hides mailbox addresses from Redis key listings.
    import hashlib
    return "webmail:events:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def publish_mailbox_change(address: str, kind: str = "changed") -> str | None:
    """Best-effort notification after the mailbox operation has succeeded.

    Returns stream ID when delivered, None when Redis is unavailable.
    Callers must never consider this a substitute for a durable mailbox write.
    """
    if kind not in _ALLOWED:
        raise ValueError("Unsupported mailbox event")
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return str(client.xadd(_key(address), {"kind": kind}, maxlen=1000, approximate=True))
    except redis.RedisError:
        logger.warning("Mailbox notification unavailable", exc_info=True)
        return None


def read_mailbox_changes(address: str, since: str = "0-0", limit: int = 50) -> list[dict[str, str]]:
    """Read scoped replay data; route must authenticate address before calling."""
    if not isinstance(since, str) or not (
        since == "0-0" or
        (len(since) <= 50 and since.count("-") == 1 and all(part.isdigit() for part in since.split("-")))
    ):
        raise ValueError("Invalid event cursor")
    count = min(max(int(limit), 1), _MAX_REPLAY)
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    rows = client.xrange(_key(address), min=f"({since}", max="+", count=count)
    return [{"id": event_id, "kind": data.get("kind", "changed")} for event_id, data in rows]
