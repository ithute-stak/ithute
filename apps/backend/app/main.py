import time
import uuid
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis import Redis
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import engine
from app.services.mail_events import publish_mail_event
from app.services.metrics import HTTP_LATENCY, HTTP_REQUESTS, READINESS, normalized_route
from app.services.signup_security import enforce_signup_rate_limit, ensure_public_signup_open
from app.services.webmail import WebmailError, session_credentials

app = FastAPI(title=settings.app_name, version="0.6.0", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBMAIL_REALTIME_MUTATION_PREFIXES = (
    "/api/v1/webmail/messages/",
    "/api/v1/webmail/drafts",
    "/api/v1/webmail/send",
    "/api/v1/webmail/send-rich",
)


def _origin(value: str) -> str:
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def _request_origin(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() or request.url.scheme.lower()
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip().lower() or request.headers.get("host", "").lower()
    return f"{scheme}://{host}" if scheme and host else ""


def _request_is_https(request: Request) -> bool:
    scheme = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() or request.url.scheme.lower()
    return scheme == "https"


def _browser_mutation_rejection(request: Request) -> str | None:
    if not request.url.path.startswith("/api/v1/") or request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return None
    supplied_origin = _origin(request.headers.get("origin", ""))
    allowed_origins = {_origin(settings.frontend_url), _request_origin(request)} - {""}
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if supplied_origin and supplied_origin not in allowed_origins:
        return "Cross-origin API mutation rejected"
    if fetch_site == "cross-site":
        return "Cross-site API mutation rejected"
    return None


def _secure_headers(response: Response, request_id: str) -> None:
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"


def _should_publish_webmail_event(request: Request, response: Response) -> bool:
    return (
        request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        and 200 <= response.status_code < 400
        and any(request.url.path.startswith(prefix) for prefix in WEBMAIL_REALTIME_MUTATION_PREFIXES)
    )


def _publish_webmail_mutation(request: Request) -> None:
    token = request.cookies.get(settings.webmail_session_cookie_name)
    if not token:
        return
    try:
        address, _ = session_credentials(token)
    except WebmailError:
        return
    publish_mail_event(
        address,
        "mailbox.changed",
        {
            "source": "webmail",
            "method": request.method.upper(),
            "path": request.url.path.removeprefix("/api/v1/webmail"),
        },
    )


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    response: Response

    try:
        if request.method.upper() == "POST" and request.url.path == "/api/v1/public/signup":
            await run_in_threadpool(ensure_public_signup_open)
            await run_in_threadpool(enforce_signup_rate_limit, request)
        rejection = _browser_mutation_rejection(request)
        if rejection:
            response = JSONResponse(status_code=403, content={"detail": rejection})
        else:
            response = await call_next(request)
    except HTTPException as exc:
        response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    if _should_publish_webmail_event(request, response):
        await run_in_threadpool(_publish_webmail_mutation, request)

    _secure_headers(response, request_id)
    if request.url.path.startswith(("/api/", "/health")):
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
    if settings.environment.lower() == "production" and _request_is_https(request):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    route = normalized_route(request)
    elapsed = time.perf_counter() - started
    HTTP_REQUESTS.labels(request.method.upper(), route, str(response.status_code)).inc()
    HTTP_LATENCY.labels(request.method.upper(), route).observe(elapsed)
    return response


app.include_router(api_router, prefix="/api/v1")


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health/live", tags=["system"])
def liveness():
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/ready", tags=["system"])
def readiness():
    dependencies = {"postgres": "ok", "redis": "ok"}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        READINESS.labels("postgres").set(1)
    except Exception:
        READINESS.labels("postgres").set(0)
        raise
    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        redis.ping()
        READINESS.labels("redis").set(1)
    except Exception:
        READINESS.labels("redis").set(0)
        raise
    return {
        "status": "ready",
        "service": settings.app_name,
        "environment": settings.environment,
        "platform_mode": settings.platform_mode,
        "dependencies": dependencies,
    }


@app.get("/health", tags=["system"])
def health():
    return readiness()
