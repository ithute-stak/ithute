import hashlib

import redis

from app.core.config import settings


class SecurityControlUnavailable(RuntimeError):
    pass


def _redis():
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _identity(address: str, client_ip: str) -> str:
    material = f"{address.strip().lower()}|{client_ip.strip()}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _attempt_key(address: str, client_ip: str) -> str:
    return f"security:webmail:login:attempts:{_identity(address, client_ip)}"


def _lock_key(address: str, client_ip: str) -> str:
    return f"security:webmail:login:locked:{_identity(address, client_ip)}"


def webmail_login_allowed(address: str, client_ip: str) -> tuple[bool, int]:
    """Return whether a mailbox login is allowed and remaining lock seconds.

    Keys contain only a SHA-256 digest of address+IP, so Redis does not retain
    plaintext mailbox identifiers as part of the abuse-control namespace.
    """
    try:
        ttl = _redis().ttl(_lock_key(address, client_ip))
    except redis.RedisError as exc:
        raise SecurityControlUnavailable("Login security controls are unavailable") from exc
    return ttl <= 0, max(ttl, 0)


def record_webmail_login_failure(address: str, client_ip: str) -> tuple[int, bool]:
    try:
        client = _redis()
        key = _attempt_key(address, client_ip)
        count = client.incr(key)
        if count == 1:
            client.expire(key, settings.webmail_login_window_seconds)
        locked = count >= settings.webmail_login_max_attempts
        if locked:
            pipe = client.pipeline(transaction=True)
            pipe.setex(_lock_key(address, client_ip), settings.webmail_login_lock_seconds, "1")
            pipe.delete(key)
            pipe.execute()
        return int(count), locked
    except redis.RedisError as exc:
        raise SecurityControlUnavailable("Login security controls are unavailable") from exc


def clear_webmail_login_failures(address: str, client_ip: str) -> None:
    try:
        client = _redis()
        client.delete(_attempt_key(address, client_ip), _lock_key(address, client_ip))
    except redis.RedisError as exc:
        raise SecurityControlUnavailable("Login security controls are unavailable") from exc
