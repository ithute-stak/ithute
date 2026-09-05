from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from database.session import get_db
from utils.central_auth import require_central_claims, resolve_tutor_user
from utils.decode_encode_token import create_access_token


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
):
    """Resolve a Tutor user from a central !thute Auth access token.

    The access token can be supplied as a Bearer token (mobile/API clients) or
    through the HttpOnly Tutor access cookie issued by the OIDC callback.
    """
    claims = require_central_claims(request)
    return resolve_tutor_user(db, claims)


def authenticate_user(user):
    """Legacy Tutor JWT issuance used only while migration mode is enabled."""
    return create_access_token(data={"user_id": str(user.id), "role": str(user.role)})
