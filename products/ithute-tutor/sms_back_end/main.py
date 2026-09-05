from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from database.config.config import settings
from database.session import engine
from mpesa import mpesa
from routes import (
    academic_core,
    administration,
    admissions,
    auth,
    class_route,
    curriculum,
    grade,
    learning_exchange,
    learning_review,
    lms,
    notification,
    onboarding,
    person,
    portal,
    quiz,
    report_exports,
    reports,
    school,
    school_classes,
    school_operations,
    student_attendance,
    student_support,
    student_transfers,
    students,
    teacher,
    tutor_coach,
)
from routes.finance_management import feeConfiguration, feePlan, feeInvoice, feePayment
from routes.finance_management.employee_managemen import (
    employee_management,
    employee_credits,
    employee_payments,
    school_admin,
    school_vice_principal,
    school_principal,
)
from routes.social import feed
from utils.authContextMiddleware import AuthContextMiddleware
from utils.startup_seed import run_startup_seed
from ws import connection_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database structure is owned by Alembic and the container entrypoint.
    # Runtime startup performs seed/backfill only and never creates tables.
    run_startup_seed()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="!thute Tutor API",
    version="3.2.0",
    description=(
        "Unified education, learning and multi-tenant school management API for !thute Tutor. "
        "Identity is provided by central !thute Auth; each active school workspace isolates its "
        "operational records while approved learning resources, longitudinal learner mastery and "
        "transfer-authorized history move safely with the learner."
    ),
)

app.mount("/media", StaticFiles(directory="media"), name="media")
app.add_middleware(AuthContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.TUTOR_FRONTEND_URL.rstrip("/"),
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "ithute-tutor", "version": "3.2.0"}


@app.get("/readyz")
def readyz():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        response = httpx.get(settings.auth_jwks_url, timeout=3.0)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload.get("keys"), list) or not payload["keys"]:
            raise RuntimeError("central Auth JWKS is empty")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Tutor dependency not ready: {exc}") from exc
    return {"status": "ready", "service": "ithute-tutor", "database": "ok", "auth": "ok"}


@app.get("/health/dependencies")
def dependency_health():
    result = {"auth": "unknown", "push": "unknown"}
    try:
        auth_response = httpx.get(settings.auth_jwks_url, timeout=3.0)
        auth_response.raise_for_status()
        result["auth"] = "ok"
    except Exception:
        result["auth"] = "unavailable"
    try:
        push_response = httpx.get(f"{settings.PUSH_BASE_URL.rstrip('/')}/readyz", timeout=3.0)
        push_response.raise_for_status()
        result["push"] = "ok"
    except Exception:
        result["push"] = "unavailable"
    return result


app.include_router(onboarding.router)
app.include_router(school.router)
app.include_router(person.router)
app.include_router(students.router)
app.include_router(student_transfers.router)
app.include_router(teacher.router)
app.include_router(grade.router)
app.include_router(class_route.router)
app.include_router(school_classes.router)
app.include_router(academic_core.router)
app.include_router(curriculum.router)
app.include_router(learning_exchange.router)
app.include_router(learning_review.router)
app.include_router(lms.router)
app.include_router(quiz.router)
app.include_router(tutor_coach.router)
app.include_router(admissions.router)
app.include_router(portal.router)
app.include_router(student_support.router)
app.include_router(school_operations.router)
app.include_router(administration.router)
app.include_router(reports.router)
app.include_router(report_exports.router)
app.include_router(student_attendance.router)
app.include_router(feeConfiguration.router)
app.include_router(feePlan.router)
app.include_router(feeInvoice.router)
app.include_router(feePayment.router)
app.include_router(employee_management.router)
app.include_router(auth.router)
app.include_router(mpesa.router)
app.include_router(connection_api.router)
app.include_router(employee_payments.router)
app.include_router(employee_credits.router)
app.include_router(school_admin.router)
app.include_router(school_vice_principal.router)
app.include_router(school_principal.router)
app.include_router(feed.router)
app.include_router(notification.router)
