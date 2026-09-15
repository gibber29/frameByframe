from fastapi import APIRouter

from backend.app.api.v1.routes import albumnesia, badly, catalog, game, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(catalog.router)
api_router.include_router(game.router)
api_router.include_router(albumnesia.router)
api_router.include_router(badly.router)
