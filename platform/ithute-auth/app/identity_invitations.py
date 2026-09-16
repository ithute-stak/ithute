from __future__ import annotations

import hmac
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .delivery import DeliveryUnavailable, send_email, send_sms
from .identity_invitation_models import IdentityInvitation
from .identity_invitation_schemas import (
    IdentityInvitationActivationRequest,
    IdentityInvitationActivationResponse,
    IdentityInvitationResponse,
    TrustedIdentityInvitationRequest,
)
from .models import User, utcnow
from .security import (
    hash_password,
    hash_security_token,
    new_numeric_code,
    new_security_token,
    normalize_email,
    normalize_phone,
    verify_password,
)
from .security_service import enqueue_auth_event, record_audit
from .service_authorization import ServiceContext, require_managed_service_scope


INVITATION_TTL = timedelta(hours=24)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ACTIVATION_ATTEMPTS = 8

platform_router = APIRouter(prefix="/v1/platform/identity-invitations", tags=["trusted-identity-invitations"])
public_router = APIRouter(prefix="/v1/identity-invitations", tags=["identity-activation"])


def _resolve_existing_identity(db: Session, *, email: str | None, phone: str | None) -> User | None:
    by_email = db.scalar(select(User).where(User.email == email)) if email else None
    by_phone = db.scalar(select(User).where(User.phone == phone)) if phone else None
    if by_email is not None and by_phone is not None and by_email.id != by_phone.id:
        raise HTTPException(status_code=409, detail="email and phone belong to different Ithute identities")
    return by_email or by_phone


def _validate_existing_identity_target(
    user: User | None,
    *,
    preferred_channel: str,
    email: str | None,
    phone: str | None,
) -> None:
    if user is None:
        return
    if preferred_channel == "phone" and (not phone or user.phone != phone):
        raise HTTPException(
            status_code=409,
            detail="existing Ithute identity must be invited through its registered phone",
        )
    if preferred_channel == "email" and (not email or user.email != email):
        raise HTTPException(
            status_code=409,
            detail="existing Ithute identity must be invited through its registered email",
        )


def _response(db: Session, invitation: IdentityInvitation) -> IdentityInvitationResponse:
    existing = _resolve_existing_identity(db, email=invitation.email, phone=invitation.phone)
    return IdentityInvitationResponse(
        id=invitation.id,
        source_client_id=invitation.source_client_id,
        external_reference=invitation.external_reference,
        display_name=invitation.display_name,
        email=invitation.email,
        phone=invitation.phone,
        preferred_channel=invitation.preferred_channel,
        status=invitation.status,
        delivery_status=invitation.delivery_status,
        expires_at=invitation.expires_at,
        existing_identity=existing is not None,
    )


def _refresh_challenge(invitation: IdentityInvitation) -> tuple[str, str]:
    token = new_security_token()
    code = new_numeric_code()
    invitation.challenge_token_hash = hash_security_token(token)
    invitation.challenge_code_hash = hash_password(code)
    invitation.expires_at = utcnow() + INVITATION_TTL
    invitation.activation_attempts = 0
    invitation.status = "pending"
    invitation.cancelled_at = None
    invitation.delivery_status = "pending"
    return token, code


def _deliver(
    *,
    invitation: IdentityInvitation,
    token: str,
    code: str,
    settings: Settings,
) -> None:
    base_url = settings.account_base_url.rstrip("/")
    if invitation.preferred_channel == "phone":
        if not invitation.phone:
            raise DeliveryUnavailable("phone target unavailable")
        activation_url = f"{base_url}/account/activate?invitation={invitation.id}"
        send_sms(
            settings,
            phone=invitation.phone,
            message=(
                f"Ithute identity activation for {invitation.display_name}. "
                f"Code: {code}. Open {activation_url}. This code expires in 24 hours. "
                "Do not share this code."
            ),
        )
        return

    if not invitation.email:
        raise DeliveryUnavailable("email target unavailable")
    activation_url = f"{base_url}/account/activate?invitation={invitation.id}&token={token}"
    send_email(
        settings,
        recipient=invitation.email,
        subject="Activate your Ithute identity",
        body=(
            f"Hello {invitation.display_name},\n\n"
            "A trusted Ithute service has invited you to activate your central Ithute identity.\n\n"
            f"Activate securely: {activation_url}\n\n"
            "This activation link expires in 24 hours. If you did not expect this invitation, you can ignore it."
        ),
    )


def _attempt_delivery(
    db: Session,
    *,
    invitation: IdentityInvitation,
    token: str,
    code: str,
    settings: Settings,
    request: Request,
    event_type: str,
) -> None:
    try:
        _deliver(invitation=invitation, token=token, code=code, settings=settings)
    except Exception as exc:  # delivery adapters can fail at SMTP/HTTP/network boundaries
        invitation.delivery_status = "failed"
        record_audit(
            db,
            event_type="trusted_identity_invitation_delivery_failed",
            success=False,
            client_id=invitation.source_client_id,
            request=request,
            details={
                "invitation_id": str(invitation.id),
                "channel": invitation.preferred_channel,
                "error_type": type(exc).__name__,
            },
        )
        return

    invitation.delivery_status = "sent"
    invitation.last_sent_at = utcnow()
    record_audit(
        db,
        event_type=event_type,
        client_id=invitation.source_client_id,
        request=request,
        details={
            "invitation_id": str(invitation.id),
            "channel": invitation.preferred_channel,
            "external_reference": invitation.external_reference,
        },
    )


@platform_router.post("", response_model=IdentityInvitationResponse, status_code=201)
def create_identity_invitation(
    payload: TrustedIdentityInvitationRequest,
    request: Request,
    context: ServiceContext = Depends(require_managed_service_scope("identity.invite")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IdentityInvitationResponse:
    email = normalize_email(str(payload.email) if payload.email else None)
    phone = normalize_phone(payload.phone)
    existing_identity = _resolve_existing_identity(db, email=email, phone=phone)
    _validate_existing_identity_target(
        existing_identity,
        preferred_channel=payload.preferred_channel,
        email=email,
        phone=phone,
    )

    reference = payload.external_reference.strip()
    invitation = db.scalar(
        select(IdentityInvitation).where(
            IdentityInvitation.source_client_id == context.client_id,
            IdentityInvitation.external_reference == reference,
        )
    )
    if invitation is not None and invitation.consumed_at is not None:
        return _response(db, invitation)

    created = invitation is None
    if invitation is None:
        # Use unique temporary challenge digests before the first flush so the
        # database never sees a shared placeholder in a unique column.
        invitation = IdentityInvitation(
            source_client_id=context.client_id,
            external_reference=reference,
            display_name=payload.display_name.strip(),
            email=email,
            phone=phone,
            preferred_channel=payload.preferred_channel,
            challenge_token_hash=hash_security_token(new_security_token()),
            challenge_code_hash=hash_password(new_numeric_code()),
            expires_at=utcnow() + INVITATION_TTL,
        )
        db.add(invitation)
        db.flush()
    else:
        invitation.display_name = payload.display_name.strip()
        invitation.email = email
        invitation.phone = phone
        invitation.preferred_channel = payload.preferred_channel

    token, code = _refresh_challenge(invitation)
    record_audit(
        db,
        event_type="trusted_identity_invitation_created" if created else "trusted_identity_invitation_refreshed",
        client_id=context.client_id,
        request=request,
        details={
            "invitation_id": str(invitation.id),
            "external_reference": invitation.external_reference,
            "channel": invitation.preferred_channel,
        },
    )
    _attempt_delivery(
        db,
        invitation=invitation,
        token=token,
        code=code,
        settings=settings,
        request=request,
        event_type="trusted_identity_invitation_sent",
    )
    db.commit()
    db.refresh(invitation)
    return _response(db, invitation)


@platform_router.post("/{invitation_id}/resend", response_model=IdentityInvitationResponse)
def resend_identity_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    context: ServiceContext = Depends(require_managed_service_scope("identity.invite")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IdentityInvitationResponse:
    invitation = db.get(IdentityInvitation, invitation_id)
    if invitation is None or invitation.source_client_id != context.client_id:
        raise HTTPException(status_code=404, detail="invitation not found")
    if invitation.consumed_at is not None:
        raise HTTPException(status_code=409, detail="invitation already activated")
    if invitation.last_sent_at is not None and utcnow() - invitation.last_sent_at < RESEND_COOLDOWN:
        raise HTTPException(status_code=429, detail="wait before resending this invitation")

    existing_identity = _resolve_existing_identity(db, email=invitation.email, phone=invitation.phone)
    _validate_existing_identity_target(
        existing_identity,
        preferred_channel=invitation.preferred_channel,
        email=invitation.email,
        phone=invitation.phone,
    )
    token, code = _refresh_challenge(invitation)
    _attempt_delivery(
        db,
        invitation=invitation,
        token=token,
        code=code,
        settings=settings,
        request=request,
        event_type="trusted_identity_invitation_resent",
    )
    db.commit()
    db.refresh(invitation)
    return _response(db, invitation)


@platform_router.post("/{invitation_id}/cancel", response_model=IdentityInvitationResponse)
def cancel_identity_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    context: ServiceContext = Depends(require_managed_service_scope("identity.invite")),
    db: Session = Depends(get_db),
) -> IdentityInvitationResponse:
    invitation = db.get(IdentityInvitation, invitation_id)
    if invitation is None or invitation.source_client_id != context.client_id:
        raise HTTPException(status_code=404, detail="invitation not found")
    if invitation.consumed_at is not None:
        raise HTTPException(status_code=409, detail="invitation already activated")
    invitation.status = "cancelled"
    invitation.cancelled_at = utcnow()
    record_audit(
        db,
        event_type="trusted_identity_invitation_cancelled",
        client_id=context.client_id,
        request=request,
        details={"invitation_id": str(invitation.id), "external_reference": invitation.external_reference},
    )
    db.commit()
    db.refresh(invitation)
    return _response(db, invitation)


@platform_router.get("/{invitation_id}", response_model=IdentityInvitationResponse)
def get_identity_invitation(
    invitation_id: uuid.UUID,
    context: ServiceContext = Depends(require_managed_service_scope("identity.invite")),
    db: Session = Depends(get_db),
) -> IdentityInvitationResponse:
    invitation = db.get(IdentityInvitation, invitation_id)
    if invitation is None or invitation.source_client_id != context.client_id:
        raise HTTPException(status_code=404, detail="invitation not found")
    return _response(db, invitation)


def activate_identity_invitation(
    payload: IdentityInvitationActivationRequest,
    *,
    request: Request,
    db: Session,
    settings: Settings,
) -> IdentityInvitationActivationResponse:
    invitation = db.get(IdentityInvitation, payload.invitation_id)
    now = utcnow()
    if invitation is None:
        raise HTTPException(status_code=404, detail="activation invitation not found")
    if invitation.consumed_at is not None:
        if invitation.user_id is None:
            raise HTTPException(status_code=409, detail="invitation already used")
        return IdentityInvitationActivationResponse(
            sub=str(invitation.user_id),
            existing_identity=True,
            sign_in_url=f"{settings.account_base_url.rstrip('/')}/account/login",
        )
    if invitation.cancelled_at is not None or invitation.status in {"cancelled", "locked"}:
        raise HTTPException(status_code=410, detail="activation invitation is no longer valid")
    if invitation.expires_at <= now:
        invitation.status = "expired"
        record_audit(
            db,
            event_type="trusted_identity_invitation_expired",
            success=False,
            client_id=invitation.source_client_id,
            request=request,
            details={"invitation_id": str(invitation.id)},
        )
        db.commit()
        raise HTTPException(status_code=410, detail="activation invitation expired")
    if invitation.activation_attempts >= MAX_ACTIVATION_ATTEMPTS:
        invitation.status = "locked"
        db.commit()
        raise HTTPException(status_code=410, detail="activation invitation is no longer valid")

    challenge_valid = False
    if payload.token:
        challenge_valid = hmac.compare_digest(
            invitation.challenge_token_hash,
            hash_security_token(payload.token),
        )
    if not challenge_valid and payload.code:
        challenge_valid = verify_password(payload.code.strip(), invitation.challenge_code_hash)

    if not challenge_valid:
        invitation.activation_attempts += 1
        if invitation.activation_attempts >= MAX_ACTIVATION_ATTEMPTS:
            invitation.status = "locked"
        record_audit(
            db,
            event_type="trusted_identity_invitation_activation_failed",
            success=False,
            client_id=invitation.source_client_id,
            request=request,
            details={
                "invitation_id": str(invitation.id),
                "attempts": invitation.activation_attempts,
            },
        )
        db.commit()
        raise HTTPException(status_code=401, detail="invalid activation challenge")

    user = _resolve_existing_identity(db, email=invitation.email, phone=invitation.phone)
    _validate_existing_identity_target(
        user,
        preferred_channel=invitation.preferred_channel,
        email=invitation.email,
        phone=invitation.phone,
    )
    existing_identity = user is not None
    if user is not None and not user.is_active:
        record_audit(
            db,
            event_type="trusted_identity_invitation_activation_blocked",
            user=user,
            success=False,
            client_id=invitation.source_client_id,
            request=request,
            details={"invitation_id": str(invitation.id), "reason": "account_disabled"},
        )
        db.commit()
        raise HTTPException(status_code=403, detail="existing Ithute identity is disabled")

    if user is None:
        if not payload.password:
            raise HTTPException(status_code=422, detail="password is required for a new Ithute identity")
        user = User(
            email=invitation.email,
            phone=invitation.phone,
            display_name=invitation.display_name,
            password_hash=hash_password(payload.password),
            email_verified=invitation.preferred_channel == "email",
            phone_verified=invitation.preferred_channel == "phone",
            is_active=True,
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="identity contact information is already registered") from None
    else:
        if invitation.preferred_channel == "email" and invitation.email and user.email == invitation.email:
            user.email_verified = True
        if invitation.preferred_channel == "phone" and invitation.phone and user.phone == invitation.phone:
            user.phone_verified = True

    invitation.user_id = user.id
    invitation.status = "activated"
    invitation.consumed_at = now
    invitation.delivery_status = "completed"
    record_audit(
        db,
        event_type="trusted_identity_invitation_activated",
        user=user,
        client_id=invitation.source_client_id,
        request=request,
        details={
            "invitation_id": str(invitation.id),
            "external_reference": invitation.external_reference,
            "existing_identity": existing_identity,
            "verified_channel": invitation.preferred_channel,
        },
    )
    enqueue_auth_event(
        db,
        event_type="identity.invitation_activated",
        user_id=user.id,
        client_id=invitation.source_client_id,
        details={
            "invitation_id": str(invitation.id),
            "external_reference": invitation.external_reference,
            "existing_identity": existing_identity,
        },
    )
    db.commit()
    return IdentityInvitationActivationResponse(
        sub=str(user.id),
        existing_identity=existing_identity,
        sign_in_url=f"{settings.account_base_url.rstrip('/')}/account/login",
    )


@public_router.post("/activate", response_model=IdentityInvitationActivationResponse)
def activate_identity_invitation_api(
    payload: IdentityInvitationActivationRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IdentityInvitationActivationResponse:
    return activate_identity_invitation(payload, request=request, db=db, settings=settings)
