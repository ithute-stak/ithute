from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.v1.external_webmail import (
    EXTERNAL_COOKIE,
    _client_ip,
    _failure,
    _record_auth_failure,
    _security_event,
)
from app.core.config import settings
from app.db.session import get_db
from app.services.external_webmail import ExternalWebmailError, delete_session
from app.services.external_webmail_setup import ExternalSetupError, connect_known_external_account
from app.services.security_controls import (
    SecurityControlUnavailable,
    clear_webmail_login_failures,
    webmail_login_allowed,
)

router = APIRouter(prefix="/webmail/external", tags=["external-webmail"])


class KnownExternalLogin(BaseModel):
    address: EmailStr
    password: str = Field(min_length=1, max_length=512)


@router.post("/known-session")
def known_login(
    payload: KnownExternalLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Fast login for an external mailbox that iMail has verified before.

    This endpoint never performs server discovery. If the mailbox is unknown,
    callers get a quick 404 and can send the user through external setup once.
    """
    address = str(payload.address).strip().lower()
    client_ip = _client_ip(request)

    try:
        allowed, retry_after = webmail_login_allowed(address, client_ip)
    except SecurityControlUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not allowed:
        _security_event(
            db,
            request,
            address,
            "security.webmail.external.known_login.blocked",
            "rate_limited",
            retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many mailbox sign-in attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = connect_known_external_account(address=address, password=payload.password)
    except ExternalSetupError as exc:
        if exc.authentication_failed:
            _record_auth_failure(db, request, address, client_ip, exc)
            _security_event(db, request, address, "security.webmail.external.known_login.failed", "failed")
        else:
            _security_event(db, request, address, "security.webmail.external.known_login.unavailable", "failed")
        raise _failure(exc, 422) from exc
    except ExternalWebmailError as exc:
        _security_event(db, request, address, "security.webmail.external.known_login.unavailable", "failed")
        raise _failure(exc, 422) from exc

    if result is None:
        _security_event(db, request, address, "security.webmail.external.known_login.miss", "not_found")
        raise HTTPException(
            status_code=404,
            detail="This mailbox has not been connected to !THUTE Mail before.",
        )

    token = result.token
    try:
        clear_webmail_login_failures(address, client_ip)
    except SecurityControlUnavailable as exc:
        delete_session(token)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _security_event(db, request, address, "security.webmail.external.known_login.succeeded", "succeeded")
    response.set_cookie(
        EXTERNAL_COOKIE,
        token,
        max_age=settings.webmail_session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/v1/webmail/external",
    )
    return {
        "authenticated": True,
        "known_account": True,
        "provider": "external",
        **result.config.public_dict(),
    }
