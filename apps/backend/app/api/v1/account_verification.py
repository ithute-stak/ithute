import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_token
from app.db.session import get_db
from app.models import AuditLog, EmailVerificationToken, User
from app.services.signup_security import send_system_email

router = APIRouter(prefix="/public/email-verification", tags=["email-verification"])


class VerificationRequest(BaseModel):
    email: EmailStr


class VerificationComplete(BaseModel):
    token: str = Field(min_length=20, max_length=256)


@router.post("/request")
def request_verification(payload: VerificationRequest, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    # Avoid account enumeration: always return accepted.
    if user is None or user.email_verified_at is not None:
        return {"accepted": True}

    now = datetime.now(timezone.utc)
    existing = db.scalars(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.verified_at.is_(None),
            EmailVerificationToken.expires_at > now,
        )
    ).all()
    for row in existing:
        row.expires_at = now

    raw = secrets.token_urlsafe(48)
    token = EmailVerificationToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=now + timedelta(hours=settings.email_verification_expire_hours),
    )
    db.add(token)
    db.add(AuditLog(actor_user_id=user.id, action="auth.email_verification.request", resource_type="user", resource_id=str(user.id)))
    db.commit()

    url = f"{settings.frontend_url.rstrip('/')}/verify-email?token={raw}"
    try:
        send_system_email(
            email,
            "Verify your Mailbox DNS account",
            f"Verify your email address to activate sign-in:\n\n{url}\n\nThis link expires in {settings.email_verification_expire_hours} hours.",
        )
    except RuntimeError as exc:
        if settings.environment.lower() == "production":
            raise HTTPException(status_code=503, detail="Verification email delivery is not configured") from exc

    result = {"accepted": True}
    if settings.environment.lower() != "production":
        result["verification_token"] = raw
    return result


@router.post("/verify")
def verify_email(payload: VerificationComplete, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    row = db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == hash_token(payload.token)))
    if row is None or row.verified_at is not None or row.expires_at <= now:
        raise HTTPException(status_code=400, detail="Verification token is invalid or expired")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Verification token is invalid")
    row.verified_at = now
    user.email_verified_at = now
    db.add(AuditLog(actor_user_id=user.id, action="auth.email_verification.complete", resource_type="user", resource_id=str(user.id)))
    db.commit()
    return {"verified": True, "email": user.email}
