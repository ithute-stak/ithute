from .admin import router as admin_router
from .main import app
from .platform_api import router as platform_router

app.include_router(admin_router)
app.include_router(platform_router)
