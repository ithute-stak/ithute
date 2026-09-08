from __future__ import annotations

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from database.multi_tenant_school_management.models import User
from database.session import SessionLocal
from utils.central_auth import CentralAuthError, request_access_token, validate_central_access_token
from utils.convex import current_user_id


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = request_access_token(request)
        context_token = None

        if token:
            try:
                claims = validate_central_access_token(token)
                # Make the already-verified claims available to dependencies so
                # protected routes do not validate the same JWT a second time.
                request.state.central_claims = claims
                subject = uuid.UUID(str(claims["sub"]))
                with SessionLocal() as db:
                    user = db.query(User).filter(User.auth_user_id == subject).first()
                    if user is not None:
                        context_token = current_user_id.set(str(user.id))
            except (CentralAuthError, TypeError, ValueError):
                # Protected endpoints perform the authoritative 401/403 check.
                pass

        try:
            return await call_next(request)
        finally:
            if context_token is not None:
                current_user_id.reset(context_token)
