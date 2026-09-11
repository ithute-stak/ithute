import uuid
from typing import Any, Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer = HTTPBearer(auto_error=False)
_jwks = jwt.PyJWKClient(settings.auth_jwks_url, cache_keys=True)


def decode_central_access_token(token: str) -> dict[str, Any]:
    try:
        signing_key = _jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            options={
                "require": ["iss", "sub", "aud", "sid", "iat", "nbf", "exp", "token_use"],
            },
        )
        if claims.get("token_use") != "access":
            raise ValueError("wrong token type")
        uuid.UUID(str(claims["sub"]))
        uuid.UUID(str(claims["sid"]))
        return claims
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid central access token") from exc


def current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return decode_central_access_token(credentials.credentials)
