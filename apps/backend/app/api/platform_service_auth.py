from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.ithute_auth import (
    IthuteAuthDisabled,
    IthuteAuthUnavailable,
    decode_ithute_service_token,
)


service_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class PlatformServicePrincipal:
    client_id: str
    scopes: frozenset[str]
    token_id: str


def require_platform_service_scope(required_scope: str, *, audience: str = "ithute-mail"):
    def dependency(
        credentials: HTTPAuthorizationCredentials = Depends(service_bearer),
    ) -> PlatformServicePrincipal:
        if not credentials or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Service authentication required")
        try:
            claims = decode_ithute_service_token(credentials.credentials, audience=audience)
        except IthuteAuthUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Ithute Auth verification is temporarily unavailable",
            ) from exc
        except IthuteAuthDisabled as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Platform service auth is disabled") from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token") from exc

        scopes = frozenset(str(claims.get("scope") or "").split())
        if required_scope not in scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Service scope required: {required_scope}")
        return PlatformServicePrincipal(
            client_id=str(claims["sub"]),
            scopes=scopes,
            token_id=str(claims["jti"]),
        )

    return dependency
