import hashlib
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request
from redis import Redis

from app.core.config import settings

LOGIN_WINDOW_SECONDS = 900
LOGIN_ACCOUNT_MAX_FAILURES = 8
LOGIN_SOURCE_MAX_FAILURES = 120
PASSWORD_RESET_WINDOW_SECONDS = 3600
PASSWORD_RESET_ACCOUNT_MAX_REQUESTS = 5
PASSWORD_RESET_SOURCE_MAX_REQUESTS = 30

# Application traffic reaches the backend from the local reverse proxy/Docker
# network in production. Forwarded headers must never be trusted from an
# arbitrary direct client because they are caller-controlled HTTP headers.
_TRUSTED_PROXY_NETWORKS = tuple(
    ip_network(value)
    for value in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _peer(request: Request) -> str | None:
    if request.client is None:
        return None
    value = str(request.client.host).strip()
    return value or None


def trusted_proxy_peer(peer: str | None) -> bool:
    if not peer:
        return False
    try:
        address = ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in _TRUSTED_PROXY_NETWORKS)


def request_client_ip(request: Request) -> str:
    """Return the verified client IP used for auditing and rate limiting.

    X-Real-IP is accepted only from a trusted local/private reverse proxy. An
    invalid forwarded value is ignored rather than becoming a rate-limit key.
    """
    peer = _peer(request)
    if trusted_proxy_peer(peer):
        forwarded = request.headers.get("x-real-ip", "").strip()
        if forwarded:
            try:
                return str(ip_address(forwarded))
            except ValueError:
                pass
    return peer or "unknown"


def request_is_https(request: Request) -> bool:
    """Determine HTTPS without trusting spoofable proxy headers.

    A reverse proxy may report the original scheme using X-Forwarded-Proto, but
    only when the immediate peer belongs to a trusted proxy network.
    """
    peer = _peer(request)
    if trusted_proxy_peer(peer):
        forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
        if forwarded in {"http", "https"}:
            return forwarded == "https"
    return request.url.scheme.lower() == "https"


def _source(request: Request) -> str:
    return request_client_ip(request)


def _redis() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )


def _fail_closed(exc: Exception, protection: str) -> None:
    if settings.environment.lower() == "production":
        raise HTTPException(status_code=503, detail=f"{protection} is temporarily unavailable") from exc


def _ttl_or_default(redis: Redis, key: str, default_seconds: int) -> int:
    ttl = redis.ttl(key)
    return ttl if ttl and ttl > 0 else default_seconds


def enforce_login_rate_limit(request: Request, email: str) -> None:
    account_key = f"auth:login:account:{_digest(email)}"
    source_key = f"auth:login:source:{_digest(_source(request))}"
    try:
        redis = _redis()
        account_count = int(redis.get(account_key) or 0)
        source_count = int(redis.get(source_key) or 0)
        if account_count >= LOGIN_ACCOUNT_MAX_FAILURES or source_count >= LOGIN_SOURCE_MAX_FAILURES:
            retry_after = max(
                _ttl_or_default(redis, account_key, LOGIN_WINDOW_SECONDS),
                _ttl_or_default(redis, source_key, LOGIN_WINDOW_SECONDS),
            )
            raise HTTPException(
                status_code=429,
                detail="Too many sign-in attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        _fail_closed(exc, "Sign-in protection")


def record_login_failure(request: Request, email: str) -> None:
    account_key = f"auth:login:account:{_digest(email)}"
    source_key = f"auth:login:source:{_digest(_source(request))}"
    try:
        redis = _redis()
        pipe = redis.pipeline()
        pipe.incr(account_key)
        pipe.expire(account_key, LOGIN_WINDOW_SECONDS)
        pipe.incr(source_key)
        pipe.expire(source_key, LOGIN_WINDOW_SECONDS)
        pipe.execute()
    except Exception as exc:
        _fail_closed(exc, "Sign-in protection")


def clear_login_failures(email: str) -> None:
    account_key = f"auth:login:account:{_digest(email)}"
    try:
        _redis().delete(account_key)
    except Exception as exc:
        _fail_closed(exc, "Sign-in protection")


def enforce_password_reset_rate_limit(request: Request, email: str) -> None:
    account_key = f"auth:reset:account:{_digest(email)}"
    source_key = f"auth:reset:source:{_digest(_source(request))}"
    try:
        redis = _redis()
        account_count = int(redis.get(account_key) or 0)
        source_count = int(redis.get(source_key) or 0)
        if account_count >= PASSWORD_RESET_ACCOUNT_MAX_REQUESTS or source_count >= PASSWORD_RESET_SOURCE_MAX_REQUESTS:
            retry_after = max(
                _ttl_or_default(redis, account_key, PASSWORD_RESET_WINDOW_SECONDS),
                _ttl_or_default(redis, source_key, PASSWORD_RESET_WINDOW_SECONDS),
            )
            raise HTTPException(
                status_code=429,
                detail="Too many recovery requests. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        pipe = redis.pipeline()
        pipe.incr(account_key)
        pipe.expire(account_key, PASSWORD_RESET_WINDOW_SECONDS)
        pipe.incr(source_key)
        pipe.expire(source_key, PASSWORD_RESET_WINDOW_SECONDS)
        pipe.execute()
    except HTTPException:
        raise
    except Exception as exc:
        _fail_closed(exc, "Account recovery protection")
