import uuid

from fastapi import Depends, FastAPI, HTTPException, status
from redis import Redis
from sqlalchemy import select, text

from .auth import current_claims
from .config import settings
from .db import SessionLocal, engine
from .file_compat import router as file_compat_router
from .fleet import router as fleet_router
from .fleet_advisor import router as fleet_advisor_router
from .fleet_alerts_api import router as fleet_alerts_router
from .fleet_inventory import router as fleet_inventory_router
from .fleet_reports import router as fleet_reports_router
from .fleet_views import router as fleet_views_router
from .models import Profile

app = FastAPI(title="NBros API", version="1.0.0", redoc_url=None)
app.include_router(fleet_router)
app.include_router(fleet_views_router)
app.include_router(fleet_alerts_router)
app.include_router(fleet_inventory_router)
app.include_router(fleet_reports_router)
app.include_router(fleet_advisor_router)
app.include_router(file_compat_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "nbros-api"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        redis_client.ping()
        redis_client.close()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="dependency unavailable") from exc
    return {"status": "ready", "database": "ok", "redis": "ok"}


@app.get("/api/v1/me")
def me(claims: dict = Depends(current_claims)) -> dict[str, str | None]:
    auth_user_id = uuid.UUID(str(claims["sub"]))
    token_email = claims.get("email")
    email = str(token_email).strip().lower() if token_email else None

    with SessionLocal() as db:
        profile = db.scalar(select(Profile).where(Profile.auth_user_id == auth_user_id))
        if profile is None:
            if not email or email != settings.bootstrap_admin_email.strip().lower():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NBros account is not provisioned")
            profile = Profile(auth_user_id=auth_user_id, email_snapshot=email, role="admin")
            db.add(profile)
            db.commit()
            db.refresh(profile)
        elif email and profile.email_snapshot != email:
            profile.email_snapshot = email
            db.commit()

        return {
            "id": str(profile.id),
            "auth_user_id": str(profile.auth_user_id),
            "email": profile.email_snapshot,
            "role": profile.role,
        }
