from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .managed_service_models import ManagedServiceClient
from .models import utcnow
from .security import decode_access_token
from .service_clients import decode_capabilities


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ServiceContext:
    client_id: str
    scopes: frozenset[str]
    audience: str


def require_managed_service_scope(required_scope: str, *, audience: str = "ithute-auth"):
    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        db: Session = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> ServiceContext:
        if credentials is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing service token")
        try:
            claims = decode_access_token(credentials.credentials, settings)
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token") from None

        if claims.get("token_use") != "service":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")
        token_audience = claims.get("aud")
        client_id = claims.get("azp")
        subject = claims.get("sub")
        scope_claim = claims.get("scope", "")
        if token_audience != audience or not isinstance(client_id, str) or subject != f"service:{client_id}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")
        scopes = frozenset(part for part in str(scope_claim).split(" ") if part)
        if required_scope not in scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="service scope required")

        # Only database-managed identities may call new platform APIs. Legacy
        # runtime-secret clients remain supported for older integrations but do
        # not inherit new capabilities such as identity.invite.
        client = db.scalar(select(ManagedServiceClient).where(ManagedServiceClient.client_id == client_id))
        now = utcnow()
        if client is None or not client.is_active or (client.expires_at is not None and client.expires_at <= now):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="service client unavailable")
        allowed_scopes = set(decode_capabilities(client.allowed_scopes_json))
        allowed_audiences = set(decode_capabilities(client.allowed_audiences_json))
        if required_scope not in allowed_scopes or audience not in allowed_audiences:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="service capability revoked")
        return ServiceContext(client_id=client_id, scopes=scopes, audience=audience)

    return dependency
