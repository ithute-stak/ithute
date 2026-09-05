import time

from .hub import hub


class RateLimitExceeded(RuntimeError):
    pass


async def enforce_rate_limit(namespace: str, identity: str, *, limit: int, window_seconds: int) -> None:
    if limit <= 0:
        return
    bucket = int(time.time()) // max(1, window_seconds)
    key = f"ithute:realtime:ratelimit:{namespace}:{identity}:{bucket}"
    value = await hub.redis.incr(key)
    if value == 1:
        await hub.redis.expire(key, window_seconds + 2)
    if value > limit:
        raise RateLimitExceeded(f"rate limit exceeded for {namespace}")
