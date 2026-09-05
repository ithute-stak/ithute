from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import User
from database.multi_tenant_school_management.models.enum.user_role import UserRole
from database.multi_tenant_school_management.schemas.user import UserRead
from database.session import get_db
from utils.central_auth import require_central_claims


router = APIRouter(prefix="/onboarding", tags=["Tutor Onboarding"])


class ProvisionTutorProfileRequest(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    email: EmailStr


def _normalized_email(value: str) -> str:
    return value.strip().lower()


@router.post("/profile", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def provision_tutor_profile(
    payload: ProvisionTutorProfileRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a Tutor-local profile for a first-time central !thute user.

    This endpoint never links by email. The central JWT sub is the authoritative
    identity. If a legacy Tutor row already owns the submitted email, the user
    must use the audited existing-profile link flow instead.
    """

    claims = require_central_claims(request)
    subject = uuid.UUID(str(claims["sub"]))

    existing_subject = db.query(User).filter(User.auth_user_id == subject).first()
    if existing_subject is not None:
        return existing_subject

    submitted_email = _normalized_email(str(payload.email))
    central_email = claims.get("email")
    if central_email and _normalized_email(str(central_email)) != submitted_email:
        raise HTTPException(
            status_code=400,
            detail="Tutor profile email must match the verified central !thute email",
        )

    email_owner = db.query(User).filter(User.email == submitted_email).first()
    if email_owner is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "An existing Tutor profile already uses this email. "
                "Use the existing-profile link flow; Tutor will not merge identities by email."
            ),
        )

    user = User(
        auth_user_id=subject,
        username=payload.username.strip(),
        email=submitted_email,
        password=None,
        channel="school_admin",
        role=UserRole.school_admin,
        school_id=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
