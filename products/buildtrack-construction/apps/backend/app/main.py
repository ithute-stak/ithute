from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.ithute_access import router as ithute_access_router
from app.api.v1.router import router as api_router
from app.core.config import get_settings
from app.db.session import engine, SessionLocal
from app.models import User, UserSession
from app.realtime import hub
from app.security.access import SESSION_COOKIE, token_hash
from app.security.rate_limit import AuthenticationRateLimiter

settings = get_settings()

app = FastAPI(
    title="Nthane Brothers Construction Management API",
    description="Integrated construction operations API for Nthane Brothers, developed by Ithute Solution.",
    version="0.2.0",
    docs_url="/docs",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth_rate_limiter = AuthenticationRateLimiter(
    settings.redis_url,
    settings.rate_limit_per_minute,
    settings.environment,
)

AUTH_RATE_PATHS = {
    "/api/v1/access/login",
    "/api/v1/access/oidc/login",
    "/api/v1/access/oidc/callback",
    "/api/v1/access/central-refresh",
}
LEGACY_PUBLIC_AUTH_PATHS = {
    "/api/v1/access/login",
    "/api/v1/access/bootstrap-admin",
    "/api/v1/access/reset-password",
}


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:80] or "unknown"
    return request.client.host[:80] if request.client else "unknown"


@app.middleware("http")
async def production_controls(request: Request, call_next):
    path = request.url.path

    if not settings.legacy_auth_enabled and path in LEGACY_PUBLIC_AUTH_PATHS:
        return JSONResponse(
            {"detail": "Local BuildTrack password authentication is disabled; use central Ithute Auth"},
            status_code=410,
        )

    if path in AUTH_RATE_PATHS:
        allowed, store_available = auth_rate_limiter.check(_client_key(request))
        if not store_available:
            return JSONResponse(
                {"detail": "Authentication controls are temporarily unavailable"},
                status_code=503,
                headers={"Retry-After": "5"},
            )
        if not allowed:
            return JSONResponse(
                {"detail": "Too many authentication requests; try again shortly"},
                status_code=429,
                headers={"Retry-After": "60"},
            )

    response = await call_next(request)
    principal = getattr(request.state, "principal", None)
    if (
        principal
        and response.status_code < 400
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and path.startswith("/api/v1/")
    ):
        await hub.send(
            principal.user.company_id,
            {"type": "ENTITY_CHANGED", "path": path, "method": request.method},
        )

    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(self), microphone=(), geolocation=(self)",
            "Content-Security-Policy": (
                "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                "connect-src 'self' https://auth.ithute.co.ls https://push.ithute.co.ls "
                "https://realtime.ithute.co.ls wss://realtime.ithute.co.ls"
            ),
        }
    )
    if settings.environment.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# OIDC is registered before the legacy access router so central identity owns
# the production sign-in/logout lifecycle while the existing product RBAC APIs
# remain unchanged.
app.include_router(ithute_access_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")


@app.websocket("/api/v1/realtime")
async def realtime(websocket: WebSocket):
    db = SessionLocal()
    user = None
    try:
        session = db.query(UserSession).filter(
            UserSession.token_hash == token_hash(websocket.cookies.get(SESSION_COOKIE) or "")
        ).first()
        user = db.get(User, session.user_id) if session else None
        if not session or session.revoked_at or not user or not user.is_active:
            await websocket.close(code=4401)
            return
        await hub.connect(user.company_id, websocket)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if user:
            hub.leave(user.company_id, websocket)
        db.close()


@app.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database is not ready") from error
    return {"status": "ready"}


@app.get("/health/deployment", tags=["health"])
def deployment_status() -> dict[str, object]:
    return {
        "status": "ready",
        "environment": settings.environment,
        "public_url": settings.public_app_url,
        "ports": {"frontend": 3004, "api": 8004},
        "identity": {
            "provider": "Ithute Auth",
            "issuer": settings.auth_issuer,
            "client_id": settings.auth_audience,
            "legacy_login_enabled": settings.legacy_auth_enabled,
        },
        "platform": {
            "push": bool(settings.push_base_url),
            "realtime": bool(settings.realtime_public_url),
        },
        "controls": [
            "database_readiness",
            "security_headers",
            "redis_backed_auth_rate_limit",
            "central_oidc_identity",
            "cors",
        ],
    }
