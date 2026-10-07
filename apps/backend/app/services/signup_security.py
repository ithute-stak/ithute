import smtplib
import ssl
from email.message import EmailMessage

from fastapi import HTTPException, Request
from redis import Redis

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.platform_mode import effective_platform_mode, public_signup_enabled


def ensure_public_signup_open() -> None:
    """Keep customer signup closed until the production domain is authoritative.

    ``PLATFORM_MODE=domain`` is the explicit production declaration. Persisted
    domain_pending/domain_verified states remain authoritative, while a stale
    bootstrap row from an older deployment no longer keeps a domain deployment
    closed forever.
    """
    if settings.environment.lower() != "production":
        return
    with SessionLocal() as db:
        mode = effective_platform_mode(db)
        if mode != "domain_active" or not public_signup_enabled(db):
            raise HTTPException(
                status_code=503,
                detail="Customer signup opens after the platform domain is activated",
            )
    if not settings.system_email_from or not settings.system_smtp_host:
        raise HTTPException(
            status_code=503,
            detail="Customer signup is waiting for system email delivery configuration",
        )


def enforce_signup_rate_limit(request: Request) -> None:
    host = request.client.host if request.client else "unknown"
    key = f"signup-rate:{host}"
    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, settings.signup_rate_window_seconds)
    except Exception as exc:
        if settings.environment.lower() == "production":
            raise HTTPException(status_code=503, detail="Signup protection is temporarily unavailable") from exc
        return
    if count > settings.signup_rate_max_attempts:
        raise HTTPException(status_code=429, detail="Too many signup attempts. Try again later.")


def send_system_email(to_address: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    if not settings.system_email_from or not settings.system_smtp_host:
        if settings.environment.lower() == "production":
            raise RuntimeError("System email delivery is not configured")
        return
    message = EmailMessage()
    message["From"] = settings.system_email_from
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    context = ssl.create_default_context()
    if settings.system_smtp_ssl:
        client = smtplib.SMTP_SSL(settings.system_smtp_host, settings.system_smtp_port, timeout=15, context=context)
    else:
        client = smtplib.SMTP(settings.system_smtp_host, settings.system_smtp_port, timeout=15)
        client.ehlo()
        if settings.system_smtp_starttls:
            client.starttls(context=context)
            client.ehlo()
    try:
        if settings.system_smtp_username:
            client.login(settings.system_smtp_username, settings.system_smtp_password or "")
        client.send_message(message)
    finally:
        try:
            client.quit()
        except Exception:
            client.close()
