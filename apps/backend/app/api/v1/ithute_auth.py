from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_local_user, get_current_user
from app.core.security import verify_password
from app.db.session import get_db
from app.models import AuditLog, User
from app.services.ithute_auth import (
    IthuteAuthDisabled,
    IthuteAuthUnavailable,
    decode_ithute_access_token,
    ithute_auth_enabled,
)

router = APIRouter(prefix="/auth/ithute", tags=["auth"])


class IthuteLinkRequest(BaseModel):
    access_token: str = Field(min_length=100, max_length=8192)
    current_password: str = Field(min_length=6, max_length=256)


class IthuteUnlinkRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=256)


@router.get("/status")
def status_view(current: User = Depends(get_current_user)):
    return {
        "enabled": ithute_auth_enabled(),
        "linked": current.auth_user_id is not None,
        "auth_user_id": str(current.auth_user_id) if current.auth_user_id else None,
    }


@router.post("/link")
def link_account(
    payload: IthuteLinkRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_local_user),
):
    if not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current Mailbox DNS password is incorrect")

    try:
        claims = decode_ithute_access_token(payload.access_token)
    except IthuteAuthDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="!thute Auth is not enabled for Mailbox DNS",
        ) from exc
    except IthuteAuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="!thute Auth verification is temporarily unavailable",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid !thute Auth token") from exc

    central_subject = UUID(str(claims["sub"]))
    other = db.scalar(
        select(User).where(
            User.auth_user_id == central_subject,
            User.id != current.id,
        )
    )
    if other is not None:
        raise HTTPException(
            status_code=409,
            detail="This !thute account is already linked to another Mailbox DNS user",
        )
    if current.auth_user_id and current.auth_user_id != central_subject:
        raise HTTPException(
            status_code=409,
            detail="This Mailbox DNS user is already linked to a different !thute account",
        )

    current.auth_user_id = central_subject
    db.add(
        AuditLog(
            actor_user_id=current.id,
            action="auth.ithute.link",
            resource_type="user",
            resource_id=str(current.id),
        )
    )
    db.commit()
    return {
        "linked": True,
        "auth_user_id": str(central_subject),
        "message": "!thute account linked. Existing Mailbox DNS login remains available during migration.",
    }


@router.post("/unlink")
def unlink_account(
    payload: IthuteUnlinkRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_local_user),
):
    if not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current Mailbox DNS password is incorrect")
    if current.auth_user_id is None:
        return {"linked": False, "message": "No !thute account is linked."}

    previous = str(current.auth_user_id)
    current.auth_user_id = None
    db.add(
        AuditLog(
            actor_user_id=current.id,
            action="auth.ithute.unlink",
            resource_type="user",
            resource_id=str(current.id),
            metadata_json=f'{{"previous_auth_user_id":"{previous}"}}',
        )
    )
    db.commit()
    return {
        "linked": False,
        "message": "!thute account unlinked. Existing Mailbox DNS login remains available.",
    }
