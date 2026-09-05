from __future__ import annotations

import base64
import json
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .account import AuthContext, authenticated_context
from .config import Settings, get_settings
from .db import get_db
from .models import Application, AuthSession, PasskeyCredential, User, WebAuthnChallenge, utcnow
from .schemas import (
    PasskeyAuthenticationVerifyRequest,
    PasskeyRegistrationVerifyRequest,
    PasskeyRemoveRequest,
    PasskeyResponse,
    TokenResponse,
)
from .security import create_access_token, hash_refresh_token, new_refresh_token, verify_password
from .security_service import client_ip, login_rate_limited, record_audit, verify_second_factor


router = APIRouter(tags=["passkeys"])


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _from_b64url(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _enum_value(value) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _require_client(db: Session, client_id: str) -> Application:
    client = db.scalar(select(Application).where(Application.client_id == client_id, Application.is_active.is_(True)))
    if client is None:
        raise HTTPException(status_code=400, detail="invalid_client")
    return client


def _challenge(db: Session, challenge_id: str, *, purpose: str, user_id: uuid.UUID | None = None) -> WebAuthnChallenge:
    try:
        challenge_uuid = uuid.UUID(challenge_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid passkey challenge") from None
    row = db.scalar(select(WebAuthnChallenge).where(WebAuthnChallenge.id == challenge_uuid).with_for_update())
    if (
        row is None
        or row.purpose != purpose
        or row.consumed_at is not None
        or row.expires_at <= utcnow()
        or (user_id is not None and row.user_id != user_id)
    ):
        raise HTTPException(status_code=400, detail="invalid or expired passkey challenge")
    return row


def _passkey_response(row: PasskeyCredential) -> PasskeyResponse:
    return PasskeyResponse(
        id=str(row.id),
        label=row.label,
        device_type=row.device_type,
        backed_up=row.backed_up,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


@router.get("/v1/account/passkeys", response_model=list[PasskeyResponse])
def list_passkeys(
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
) -> list[PasskeyResponse]:
    rows = db.scalars(
        select(PasskeyCredential)
        .where(PasskeyCredential.user_id == context.user.id)
        .order_by(PasskeyCredential.created_at.desc())
    ).all()
    return [_passkey_response(row) for row in rows]


@router.post("/v1/account/passkeys/registration/options")
def passkey_registration_options(
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    challenge = secrets.token_bytes(32)
    row = WebAuthnChallenge(
        user_id=context.user.id,
        purpose="register",
        challenge=_b64url(challenge),
        expires_at=utcnow() + timedelta(minutes=settings.webauthn_challenge_minutes),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    existing = db.scalars(select(PasskeyCredential).where(PasskeyCredential.user_id == context.user.id)).all()
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=context.user.id.bytes,
        user_name=context.user.email or context.user.phone or str(context.user.id),
        user_display_name=context.user.display_name,
        challenge=challenge,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            for item in existing
        ],
    )
    return {"challenge_id": str(row.id), "options": json.loads(options_to_json(options))}


@router.post("/v1/account/passkeys/registration/verify", response_model=PasskeyResponse)
def passkey_registration_verify(
    payload: PasskeyRegistrationVerifyRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PasskeyResponse:
    challenge = _challenge(db, payload.challenge_id, purpose="register", user_id=context.user.id)
    if not verify_password(payload.password, context.user.password_hash):
        record_audit(db, event_type="passkey_registration", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_second_factor(db, user=context.user, code=payload.mfa_code, settings=settings):
        record_audit(db, event_type="passkey_registration", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="MFA required or invalid code")

    try:
        verification = verify_registration_response(
            credential=payload.credential,
            expected_challenge=_from_b64url(challenge.challenge),
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            require_user_verification=True,
        )
    except Exception as exc:
        record_audit(db, event_type="passkey_registration", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=400, detail="invalid passkey registration") from exc

    credential_id = _b64url(verification.credential_id)
    response = payload.credential.get("response") if isinstance(payload.credential, dict) else None
    transports = response.get("transports") if isinstance(response, dict) else None
    row = PasskeyCredential(
        user_id=context.user.id,
        credential_id=credential_id,
        public_key=_b64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        device_type=_enum_value(verification.credential_device_type),
        backed_up=bool(verification.credential_backed_up),
        transports_json=json.dumps(transports) if isinstance(transports, list) else None,
        label=(payload.label.strip() if payload.label else None),
    )
    challenge.consumed_at = utcnow()
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="passkey is already registered") from None
    record_audit(db, event_type="passkey_registered", user=context.user, request=request, details={"passkey_id": str(row.id)})
    db.commit()
    db.refresh(row)
    return _passkey_response(row)


@router.post("/v1/account/passkeys/{passkey_id}/remove", status_code=204)
def remove_passkey(
    passkey_id: uuid.UUID,
    payload: PasskeyRemoveRequest,
    request: Request,
    context: AuthContext = Depends(authenticated_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    row = db.get(PasskeyCredential, passkey_id)
    if row is None or row.user_id != context.user.id:
        raise HTTPException(status_code=404, detail="passkey not found")
    if not verify_password(payload.password, context.user.password_hash):
        record_audit(db, event_type="passkey_removed", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_second_factor(db, user=context.user, code=payload.mfa_code, settings=settings):
        record_audit(db, event_type="passkey_removed", user=context.user, success=False, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="MFA required or invalid code")
    db.delete(row)
    record_audit(db, event_type="passkey_removed", user=context.user, request=request, details={"passkey_id": str(passkey_id)})
    db.commit()


@router.post("/v1/auth/passkey/options")
def passkey_authentication_options(
    client_id: str = Query(..., min_length=1, max_length=120),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    _require_client(db, client_id)
    challenge = secrets.token_bytes(32)
    row = WebAuthnChallenge(
        purpose="authenticate",
        challenge=_b64url(challenge),
        expires_at=utcnow() + timedelta(minutes=settings.webauthn_challenge_minutes),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        challenge=challenge,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return {"challenge_id": str(row.id), "options": json.loads(options_to_json(options))}


@router.post("/v1/auth/passkey/verify", response_model=TokenResponse)
def passkey_authentication_verify(
    payload: PasskeyAuthenticationVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    _require_client(db, payload.client_id)
    if login_rate_limited(db, request=request, settings=settings):
        record_audit(db, event_type="login_rate_limited", success=False, client_id=payload.client_id, request=request)
        db.commit()
        raise HTTPException(status_code=429, detail="too many login attempts")

    challenge = _challenge(db, payload.challenge_id, purpose="authenticate")
    credential_id = payload.credential.get("id") if isinstance(payload.credential, dict) else None
    if not isinstance(credential_id, str) or not credential_id:
        raise HTTPException(status_code=400, detail="invalid passkey credential")
    passkey = db.scalar(select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id).with_for_update())
    if passkey is None:
        record_audit(db, event_type="login_failed", success=False, client_id=payload.client_id, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid passkey")
    user = db.get(User, passkey.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user unavailable")
    if user.locked_until is not None and user.locked_until > utcnow():
        raise HTTPException(status_code=401, detail="invalid passkey")

    try:
        verification = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=_from_b64url(challenge.challenge),
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=_from_b64url(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_failures:
            user.locked_until = utcnow() + timedelta(minutes=settings.login_lock_minutes)
        record_audit(db, event_type="login_failed", user=user, success=False, client_id=payload.client_id, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid passkey") from exc

    now = utcnow()
    challenge.consumed_at = now
    passkey.sign_count = verification.new_sign_count
    passkey.device_type = _enum_value(verification.credential_device_type)
    passkey.backed_up = bool(verification.credential_backed_up)
    passkey.last_used_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = client_ip(request)

    raw_refresh = new_refresh_token()
    session = AuthSession(
        user_id=user.id,
        client_id=payload.client_id,
        refresh_token_hash=hash_refresh_token(raw_refresh),
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
        expires_at=now + timedelta(days=settings.refresh_token_days),
    )
    db.add(session)
    db.flush()
    record_audit(db, event_type="passkey_login_succeeded", user=user, client_id=payload.client_id, request=request, details={"passkey_id": str(passkey.id), "session_id": str(session.id)})
    db.commit()
    db.refresh(session)

    access = create_access_token(
        settings=settings,
        user_id=user.id,
        client_id=payload.client_id,
        session_id=session.id,
        email=user.email,
        phone=user.phone,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=raw_refresh,
        expires_in=settings.access_token_minutes * 60,
    )
