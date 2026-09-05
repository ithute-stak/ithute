import hmac
import uuid
from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .account import router as account_router
from .admin import router as admin_router
from .config import Settings, get_settings
from .db import get_db
from .models import Application, AuthSession, Device, User, utcnow
from .oauth import router as oauth_router
from .passkeys import router as passkey_router
from .portal import router as portal_router
from .portal_passkeys import router as portal_passkey_router
from .recovery_portal import router as recovery_portal_router
from .schemas import (
    DeviceRequest,
    DeviceResponse,
    LoginRequest,
    LogoutRequest,
    PushTokenResponse,
    RefreshRequest,
    RegisterRequest,
    ServiceTokenRequest,
    ServiceTokenResponse,
    TokenResponse,
    UserResponse,
)
from .security import (
    create_access_token,
    create_push_access_token,
    create_service_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    normalize_email,
    normalize_phone,
    public_jwks,
    verify_password,
)
from .security_service import client_ip, login_rate_limited, record_audit, verify_second_factor


bearer = HTTPBearer(auto_error=False)
settings = get_settings()
app = FastAPI(
    title="!thute Auth",
    version="0.9.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(oauth_router)
app.include_router(account_router)
app.include_router(admin_router)
app.include_router(passkey_router)
app.include_router(portal_router)
app.include_router(portal_passkey_router)
app.include_router(recovery_portal_router)


@app.middleware("http")
async def auth_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), publickey-credentials-get=(self)",
    )

    content_type = response.headers.get("content-type", "")
    if content_type.startswith("text/html") and request.url.path != "/docs":
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'; "
            "form-action 'self'; img-src 'self' data:; connect-src 'self'; "
            "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
        )

    public_cacheable = {
        "/healthz",
        "/.well-known/openid-configuration",
        "/.well-known/jwks.json",
    }
    if request.url.path not in public_cacheable:
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Pragma", "no-cache")

    if settings.issuer.lower().startswith("https://"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.on_event("startup")
def seed_first_party_clients() -> None:
    from .db import SessionLocal

    with SessionLocal() as db:
        for client_id, name in settings.client_map.items():
            existing = db.scalar(select(Application).where(Application.client_id == client_id))
            if existing is None:
                db.add(Application(client_id=client_id, name=name, is_active=True))
            elif existing.name != name:
                existing.name = name
        db.commit()


def require_client(db: Session, client_id: str) -> Application:
    client = db.scalar(
        select(Application).where(
            Application.client_id == client_id,
            Application.is_active.is_(True),
        )
    )
    if client is None:
        raise HTTPException(status_code=400, detail="unknown client")
    return client


def user_response(user: User) -> UserResponse:
    return UserResponse(
        sub=str(user.id),
        email=user.email,
        phone=user.phone,
        display_name=user.display_name,
        email_verified=user.email_verified,
        phone_verified=user.phone_verified,
        mfa_enabled=user.totp_enabled,
    )


def _product_session(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    config: Settings,
) -> tuple[User, AuthSession, str]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        claims = decode_access_token(credentials.credentials, config)
        if claims.get("token_use") != "access":
            raise ValueError("wrong token type")
        user_id = uuid.UUID(str(claims["sub"]))
        session_id = uuid.UUID(str(claims["sid"]))
        audience = claims.get("aud")
        if not isinstance(audience, str) or not audience:
            raise ValueError("invalid audience")
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from None

    auth_session = db.get(AuthSession, session_id)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.client_id != audience
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= utcnow()
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    require_client(db, audience)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user unavailable")
    auth_session.last_seen_at = utcnow()
    return user, auth_session, audience


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
    config: Annotated[Settings, Depends(get_settings)],
) -> User:
    user, _, _ = _product_session(credentials, db, config)
    db.commit()
    return user


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "ithute-auth"}


@app.get("/.well-known/openid-configuration")
def oidc_configuration(config: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    issuer = config.issuer.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "userinfo_endpoint": f"{issuer}/oauth/userinfo",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "subject_types_supported": ["public"],
        "scopes_supported": ["openid", "profile", "email", "phone"],
    }


@app.get("/.well-known/jwks.json")
def jwks(config: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    return {"keys": public_jwks(config)}


@app.post("/v1/users/register", response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> UserResponse:
    email = normalize_email(str(payload.email) if payload.email else None)
    phone = normalize_phone(payload.phone)
    user = User(
        email=email,
        phone=phone,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.flush()
        record_audit(db, event_type="account_registered", user=user, request=request)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="email or phone already registered") from None
    db.refresh(user)
    return user_response(user)


@app.post("/v1/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    config: Annotated[Settings, Depends(get_settings)],
    user_agent: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    require_client(db, payload.client_id)
    if login_rate_limited(db, request=request, settings=config):
        record_audit(db, event_type="login_rate_limited", success=False, client_id=payload.client_id, request=request)
        db.commit()
        raise HTTPException(status_code=429, detail="too many login attempts")

    identifier_email = normalize_email(payload.identifier)
    identifier_phone = normalize_phone(payload.identifier)
    user = db.scalar(
        select(User).where(
            or_(User.email == identifier_email, User.phone == identifier_phone),
            User.is_active.is_(True),
        )
    )
    now = utcnow()
    if user is None:
        record_audit(db, event_type="login_failed", success=False, client_id=payload.client_id, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")

    if user.locked_until is not None and user.locked_until > now:
        record_audit(db, event_type="login_blocked", user=user, success=False, client_id=payload.client_id, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= config.max_login_failures:
            user.locked_until = now + timedelta(minutes=config.login_lock_minutes)
        record_audit(
            db,
            event_type="login_failed",
            user=user,
            success=False,
            client_id=payload.client_id,
            request=request,
            details={"failed_attempts": user.failed_login_attempts},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")

    if not verify_second_factor(db, user=user, code=payload.mfa_code, settings=config):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= config.max_login_failures:
            user.locked_until = now + timedelta(minutes=config.login_lock_minutes)
        record_audit(
            db,
            event_type="mfa_challenge_failed",
            user=user,
            success=False,
            client_id=payload.client_id,
            request=request,
            details={"failed_attempts": user.failed_login_attempts},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="MFA required or invalid code")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = client_ip(request)

    refresh_token = new_refresh_token()
    auth_session = AuthSession(
        user_id=user.id,
        client_id=payload.client_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        user_agent=user_agent,
        ip_address=client_ip(request),
        expires_at=now + timedelta(days=config.refresh_token_days),
    )
    db.add(auth_session)
    db.flush()
    record_audit(db, event_type="login_succeeded", user=user, client_id=payload.client_id, request=request, details={"session_id": str(auth_session.id)})
    db.commit()
    db.refresh(auth_session)

    access_token = create_access_token(
        settings=config,
        user_id=user.id,
        client_id=payload.client_id,
        session_id=auth_session.id,
        email=user.email,
        phone=user.phone,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=config.access_token_minutes * 60,
    )


@app.post("/v1/auth/push-token", response_model=PushTokenResponse)
def push_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
    config: Annotated[Settings, Depends(get_settings)],
) -> PushTokenResponse:
    user, auth_session, client_id = _product_session(credentials, db, config)
    token = create_push_access_token(
        settings=config,
        user_id=user.id,
        client_id=client_id,
        session_id=auth_session.id,
    )
    db.commit()
    return PushTokenResponse(
        access_token=token,
        expires_in=config.push_user_token_minutes * 60,
    )


@app.post("/v1/auth/service-token", response_model=ServiceTokenResponse)
def service_token(
    payload: ServiceTokenRequest,
    db: Annotated[Session, Depends(get_db)],
    config: Annotated[Settings, Depends(get_settings)],
) -> ServiceTokenResponse:
    require_client(db, payload.client_id)
    expected = config.service_client_secrets.get(payload.client_id)
    if expected is None or not hmac.compare_digest(expected, payload.client_secret):
        raise HTTPException(status_code=401, detail="invalid service credentials")
    token = create_service_token(
        settings=config,
        client_id=payload.client_id,
        audience=payload.audience,
        scope=payload.scope,
    )
    return ServiceTokenResponse(
        access_token=token,
        expires_in=config.service_token_minutes * 60,
        scope=payload.scope,
    )


@app.post("/v1/auth/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
    config: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    require_client(db, payload.client_id)
    refresh_hash = hash_refresh_token(payload.refresh_token)
    auth_session = db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == refresh_hash))
    if (
        auth_session is None
        or auth_session.client_id != payload.client_id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= utcnow()
    ):
        raise HTTPException(status_code=401, detail="invalid refresh token")

    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user unavailable")

    new_token = new_refresh_token()
    auth_session.refresh_token_hash = hash_refresh_token(new_token)
    auth_session.last_seen_at = utcnow()
    db.commit()

    access_token = create_access_token(
        settings=config,
        user_id=user.id,
        client_id=payload.client_id,
        session_id=auth_session.id,
        email=user.email,
        phone=user.phone,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_token,
        expires_in=config.access_token_minutes * 60,
    )


@app.post("/v1/auth/logout", status_code=204)
def logout(payload: LogoutRequest, db: Annotated[Session, Depends(get_db)]) -> None:
    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == hash_refresh_token(payload.refresh_token))
    )
    if auth_session is not None and auth_session.revoked_at is None:
        auth_session.revoked_at = utcnow()
        auth_session.revoked_reason = "logout"
        db.commit()


@app.get("/v1/me", response_model=UserResponse)
@app.get("/oauth/userinfo", response_model=UserResponse)
def me(user: Annotated[User, Depends(current_user)]) -> UserResponse:
    return user_response(user)


@app.post("/v1/devices", response_model=DeviceResponse)
def register_device(
    payload: DeviceRequest,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DeviceResponse:
    device = db.scalar(select(Device).where(Device.user_id == user.id, Device.device_key == payload.device_key))
    if device is None:
        device = Device(
            user_id=user.id,
            device_key=payload.device_key,
            platform=payload.platform,
            label=payload.label,
        )
        db.add(device)
    else:
        device.platform = payload.platform
        device.label = payload.label
        device.is_active = True
        device.last_seen_at = utcnow()
    db.commit()
    return DeviceResponse(
        device_key=device.device_key,
        platform=device.platform,
        label=device.label,
        active=device.is_active,
    )


@app.delete("/v1/devices/{device_key}", status_code=204)
def revoke_device(
    device_key: str,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    device = db.scalar(select(Device).where(Device.user_id == user.id, Device.device_key == device_key))
    if device is not None:
        device.is_active = False
        db.commit()
