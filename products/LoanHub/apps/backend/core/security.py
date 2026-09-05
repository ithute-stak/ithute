from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy.orm import Session, selectinload

from database.models.user import RefreshToken, User
from database.models.governance_control import UserSecurityState
from database.session import get_db
from services.ithute_auth_service import (
    IthuteAuthDisabled,
    IthuteAuthUnavailable,
    decode_ithute_access_token,
    ithute_auth_enabled,
)
from utils.decode_encode_token import create_access_token, decode_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)
DUMMY_PASSWORD_HASH = pwd_context.hash("LoanHub timing defence only 9Q!v4")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _load_user(db: Session, user_id: UUID) -> User | None:
    return (
        db.query(User)
        .options(
            selectinload(User.person),
            selectinload(User.company_staff),
            selectinload(User.borrower_profile),
        )
        .filter(User.id == user_id)
        .first()
    )


def _current_local_user(token: str, db: Session) -> User:
    payload = decode_token(token)
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise InvalidTokenError("missing LoanHub user identity")
    user_id = UUID(str(raw_user_id))
    token_session_version = int(payload.get("session_version", 1))
    token_session_jti = payload.get("session_jti")

    user = _load_user(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    state = db.query(UserSecurityState).filter(UserSecurityState.user_id == user.id).first()
    if state and int(state.session_version or 1) != token_session_version:
        raise HTTPException(status_code=401, detail="Session has been revoked")
    if token_session_jti:
        active_session = db.query(RefreshToken.id).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.jti == token_session_jti,
            RefreshToken.revoked.is_(False),
        ).first()
        if not active_session:
            raise HTTPException(status_code=401, detail="Session has been revoked")
    setattr(user, "_auth_source", "loanhub")
    return user


def get_current_local_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User:
    """Require an existing LoanHub-issued access token.

    This dependency is intentionally used by central-account linking and
    unlinking so a central identity can never attach itself to a LoanHub user
    without proof of control of the existing product account.
    """

    try:
        return _current_local_user(token, db)
    except ExpiredSignatureError as error:
        raise HTTPException(status_code=401, detail="Access token expired") from error
    except (InvalidTokenError, ValueError) as error:
        raise HTTPException(status_code=401, detail="Invalid LoanHub access token") from error


def _current_ithute_user(token: str, db: Session) -> User:
    claims = decode_ithute_access_token(token)
    auth_user_id = UUID(str(claims["sub"]))
    user = (
        db.query(User)
        .options(
            selectinload(User.person),
            selectinload(User.company_staff),
            selectinload(User.borrower_profile),
        )
        .filter(User.auth_user_id == auth_user_id)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ITHUTE_ACCOUNT_NOT_LINKED",
                "message": "This !thute account is not linked to a LoanHub account.",
            },
        )
    setattr(user, "_auth_source", "ithute")
    return user


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User:
    # Migration mode: keep all existing LoanHub tokens working. Only when a
    # token is not a valid LoanHub token do we attempt the central verifier.
    try:
        return _current_local_user(token, db)
    except ExpiredSignatureError as error:
        raise HTTPException(status_code=401, detail="Access token expired") from error
    except HTTPException:
        raise
    except (InvalidTokenError, ValueError) as local_error:
        if not ithute_auth_enabled():
            raise HTTPException(status_code=401, detail="Invalid access token") from local_error

    try:
        return _current_ithute_user(token, db)
    except ExpiredSignatureError as error:
        raise HTTPException(status_code=401, detail="Access token expired") from error
    except IthuteAuthUnavailable as error:
        raise HTTPException(
            status_code=503,
            detail="!thute Auth verification is temporarily unavailable",
        ) from error
    except IthuteAuthDisabled as error:
        raise HTTPException(status_code=401, detail="Invalid access token") from error
    except (InvalidTokenError, ValueError) as error:
        raise HTTPException(status_code=401, detail="Invalid access token") from error


def authenticate_user(
    user: User,
    *,
    session_version: int = 1,
    session_jti: str | None = None,
) -> str:
    return create_access_token(
        {
            "user_id": str(user.id),
            "role": user.role.value,
            "token_type": "access",
            "session_version": int(session_version),
            "session_jti": session_jti,
        }
    )
