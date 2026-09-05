from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.v1.external_webmail import (
    _client_ip,
    _record_auth_failure,
    _security_event,
)
from app.db.session import get_db
from app.services.external_webmail import ExternalWebmailError, delete_session, normalized_config
from app.services.external_webmail_setup import (
    ExternalSetupError,
    _persist_verified_session,
    _probe_imap,
    _probe_smtp,
)
from app.services.security_controls import (
    SecurityControlUnavailable,
    clear_webmail_login_failures,
    webmail_login_allowed,
)

router = APIRouter(prefix="/webmail/external", tags=["external-webmail"])


class VerifiedExternalLogin(BaseModel):
    address: EmailStr
    password: str = Field(min_length=1, max_length=512)
    username: str = Field(default="", max_length=320)
    display_name: str = Field(default="", max_length=255)
    imap_host: str = Field(min_length=1, max_length=253)
    imap_port: int = Field(ge=1, le=65535)
    imap_security: str = Field(min_length=1, max_length=20)
    smtp_host: str = Field(min_length=1, max_length=253)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_security: str = Field(min_length=1, max_length=20)


def _setup_error(message: str, *, authentication_failed: bool = False) -> HTTPException:
    return HTTPException(status_code=401 if authentication_failed else 422, detail=message)


@router.post("/register-known", status_code=201)
def register_verified_external(
    payload: VerifiedExternalLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    """Remember settings already discovered and verified by iMail.

    The server verifies the exact IMAP and SMTP endpoints once. It does not run
    hostname/port discovery again and does not create a browser/mobile login
    session. Later normal mailbox login uses the remembered profile directly.
    """
    address = str(payload.address).strip().lower()
    client_ip = _client_ip(request)

    try:
        allowed, retry_after = webmail_login_allowed(address, client_ip)
    except SecurityControlUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many mailbox sign-in attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        config = normalized_config(
            address=address,
            username=payload.username or address,
            password=payload.password,
            display_name=payload.display_name,
            imap_host=payload.imap_host,
            imap_port=payload.imap_port,
            imap_security=payload.imap_security,
            smtp_host=payload.smtp_host,
            smtp_port=payload.smtp_port,
            smtp_security=payload.smtp_security,
        )
    except ExternalWebmailError as exc:
        _security_event(db, request, address, "security.webmail.external.register.invalid", "failed")
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    incoming = _probe_imap(
        config.imap_host,
        config.imap_port,
        config.imap_security,
        config.username,
        config.password,
    )
    if incoming != "ok":
        auth_failed = incoming == "auth"
        exc = ExternalSetupError(
            "The saved incoming mail settings could not be verified. Check the mailbox password or IMAP settings.",
            authentication_failed=auth_failed,
        )
        if auth_failed:
            _record_auth_failure(db, request, address, client_ip, exc)
        _security_event(db, request, address, "security.webmail.external.register.imap_failed", "failed")
        raise _setup_error(str(exc), authentication_failed=auth_failed)

    outgoing = _probe_smtp(
        config.smtp_host,
        config.smtp_port,
        config.smtp_security,
        config.username,
        config.password,
    )
    if outgoing != "ok":
        auth_failed = outgoing == "auth"
        exc = ExternalSetupError(
            "Incoming mail was verified, but the saved outgoing SMTP settings could not be verified.",
            authentication_failed=auth_failed,
        )
        if auth_failed:
            _record_auth_failure(db, request, address, client_ip, exc)
        _security_event(db, request, address, "security.webmail.external.register.smtp_failed", "failed")
        raise _setup_error(str(exc), authentication_failed=auth_failed)

    # Reuse the existing atomic profile writer, then immediately remove the
    # short-lived session it creates. The long-lived known-account profile does
    # not contain the password; the password exists only in that deleted session.
    token = _persist_verified_session(config)
    try:
        delete_session(token)
        clear_webmail_login_failures(address, client_ip)
    except SecurityControlUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _security_event(db, request, address, "security.webmail.external.register.succeeded", "succeeded")
    return {
        "known_account": True,
        "address": config.address,
        "verified": True,
    }
