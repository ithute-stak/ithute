from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from database.session import get_db
from utils.central_auth import require_central_claims, resolve_tutor_user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
):
    """Resolve a Tutor user from a central !thute Auth access token.

    The access token can be supplied as a Bearer token (mobile/API clients) or
    through the HttpOnly Tutor access cookie issued by the OIDC callback.

    Central-auth request handling must remain completely independent of the
    migration-only local JWT keypair. Production disables legacy Tutor auth, so
    importing this module must never require local JWT key material.
    """
    claims = require_central_claims(request)
    return resolve_tutor_user(db, claims)


def authenticate_user(user):
    """Issue a migration-only Tutor JWT when legacy auth is explicitly used.

    Import the old signer only at the point where a legacy token is actually
    requested. This keeps central !thute Auth production startup independent of
    JWT_PRIVATE_KEY/JWT_PUBLIC_KEY and their development file-path fallbacks.
    """
    from utils.decode_encode_token import create_access_token

    return create_access_token(data={"user_id": str(user.id), "role": str(user.role)})
