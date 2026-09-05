from .main import app
from .platform_admin_authorize import router as platform_admin_authorize_router


# Privileged console authorization deliberately bypasses the normal reusable
# browser SSO shortcut: this router always asks for fresh credentials + MFA.
app.include_router(platform_admin_authorize_router, prefix="/v1/admin")
