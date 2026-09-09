from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic, time

from redis import Redis
from redis.exceptions import RedisError


class AuthenticationRateLimiter:
    """Shared authentication rate limit with a development-only memory fallback."""

    def __init__(self, redis_url: str, limit_per_minute: int, environment: str) -> None:
        self.limit = max(1, int(limit_per_minute))
        self.production = environment.strip().lower() == "production"
        self.redis = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
        self._memory: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, bool]:
        """Return (allowed, backing_store_available)."""
        window = int(time() // 60)
        redis_key = f"buildtrack:auth-rate:{window}:{key}"
        try:
            pipeline = self.redis.pipeline(transaction=True)
            pipeline.incr(redis_key)
            pipeline.expire(redis_key, 75)
            count, _ = pipeline.execute()
            return int(count) <= self.limit, True
        except RedisError:
            if self.production:
                # Authentication controls should not silently disappear if the
                # shared product Redis service is unavailable in production.
                return False, False

        now = monotonic()
        values = self._memory[key]
        while values and values[0] <= now - 60:
            values.popleft()
        if len(values) >= self.limit:
            return False, True
        values.append(now)
        return True, True
