from fastapi import FastAPI

from backend.app.api.v1.router import api_router
from backend.app.core.config import Settings, settings


def create_app(app_settings: Settings = settings) -> FastAPI:
    app = FastAPI(title=app_settings.app_name)
    app.include_router(api_router, prefix=app_settings.api_v1_prefix)
    if app_settings.admin_enabled:
        from backend.app.api.admin_ui import router as admin_ui_router
        from backend.app.api.v1.routes.admin import router as admin_api_router

        app.include_router(admin_api_router, prefix=app_settings.api_v1_prefix)
        app.include_router(admin_ui_router)
    return app


app = create_app()
