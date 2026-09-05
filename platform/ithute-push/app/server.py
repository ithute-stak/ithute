from .admin import router as admin_router
from .main import app


# Keep privileged platform routes isolated from the core device/message module.
# The production entrypoint imports this module so admin endpoints are available
# only through the same hardened FastAPI process and authentication boundary.
app.include_router(admin_router)
