from collections import defaultdict, deque
from time import monotonic
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import router as api_router
from app.core.config import get_settings
from app.db.session import engine, SessionLocal
from app.models import User, UserSession
from app.realtime import hub
from app.security.access import SESSION_COOKIE, token_hash

settings = get_settings()

app = FastAPI(
    title="Nthane Brothers Construction Management API",
    description="Integrated construction operations API for Nthane Brothers, developed by Ithute Solution.",
    version="0.1.0",
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
_requests: dict[str, deque[float]] = defaultdict(deque)
@app.middleware("http")
async def production_controls(request: Request, call_next):
    client = request.client.host if request.client else "unknown"; window = _requests[client]; now = monotonic()
    while window and window[0] <= now - 60: window.popleft()
    if request.url.path.startswith("/api/v1/access") and len(window) >= settings.rate_limit_per_minute: raise HTTPException(status_code=429, detail="Too many requests; try again shortly")
    window.append(now); response = await call_next(request)
    p = getattr(request.state, "principal", None)
    if p and response.status_code < 400 and request.method in {"POST","PUT","PATCH","DELETE"} and request.url.path.startswith("/api/v1/"): await hub.send(p.user.company_id, {"type":"ENTITY_CHANGED","path":request.url.path,"method":request.method})
    response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"strict-origin-when-cross-origin","Permissions-Policy":"camera=(), microphone=(), geolocation=()","Content-Security-Policy":"default-src 'self'; frame-ancestors 'none'; base-uri 'self'"})
    if settings.environment.lower() == "production": response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
    return response

app.include_router(api_router, prefix="/api/v1")

@app.websocket("/api/v1/realtime")
async def realtime(websocket: WebSocket):
    db = SessionLocal(); user = None
    try:
        s = db.query(UserSession).filter(UserSession.token_hash == token_hash(websocket.cookies.get(SESSION_COOKIE) or "")).first(); user = db.get(User, s.user_id) if s else None
        if not s or s.revoked_at or not user or not user.is_active: await websocket.close(code=4401); return
        await hub.connect(user.company_id, websocket)
        while True: await websocket.receive_text()
    except WebSocketDisconnect: pass
    finally:
        if user: hub.leave(user.company_id, websocket)
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
    return {"status":"ready","environment":settings.environment,"ports":{"frontend":3004,"api":8004},"controls":["database_readiness","security_headers","sensitive_endpoint_rate_limit","cors"]}
