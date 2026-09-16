from .main import app
from .platform_admin_authorize import router as platform_admin_authorize_router
from .service_client_admin import router as service_client_admin_router
from .service_token_api import router as service_token_router


# Privileged console authorization deliberately bypasses the normal reusable
# browser SSO shortcut: this router always asks for fresh credentials + MFA.
app.include_router(platform_admin_authorize_router, prefix="/v1/admin")

# main.py still carries the original environment-secret service-token endpoint
# for source compatibility. At the runtime composition boundary replace that
# route with the managed-client implementation, which itself keeps a temporary
# fallback for older integrations not migrated to the database yet.
app.router.routes = [
    route
    for route in app.router.routes
    if not (
        getattr(route, "path", None) == "/v1/auth/service-token"
        and "POST" in (getattr(route, "methods", set()) or set())
    )
]
app.include_router(service_token_router)
app.include_router(service_client_admin_router)
