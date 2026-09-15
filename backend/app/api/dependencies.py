import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.session import get_db
from backend.app.repositories import AlbumnesiaGameRepository, BadlyGameRepository, CategoryRepository, ContentRepository, GameRepository, MovieRepository, PuzzleRepository, ScheduleRepository
from backend.app.security import GuestTokenManager
from backend.app.services import AlbumnesiaGameService, BadlyGameService, CatalogService, ContentManagementService, GameplayService, PuzzleAuthoringService, SchedulingService
from backend.app.storage import LocalAssetStorage

DatabaseSession = Annotated[Session, Depends(get_db)]


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    expected = settings.admin_token
    if not expected or x_admin_token is None or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Valid admin credentials are required")


AdminMutation = Annotated[None, Depends(require_admin)]


def get_catalog_service(session: DatabaseSession) -> CatalogService:
    return CatalogService(CategoryRepository(session), MovieRepository(session))


CatalogServiceDependency = Annotated[CatalogService, Depends(get_catalog_service)]


def get_asset_storage() -> LocalAssetStorage:
    return LocalAssetStorage(settings.asset_root)


AssetStorageDependency = Annotated[LocalAssetStorage, Depends(get_asset_storage)]


def get_puzzle_authoring_service(
    session: DatabaseSession, storage: AssetStorageDependency
) -> PuzzleAuthoringService:
    return PuzzleAuthoringService(PuzzleRepository(session), storage)


PuzzleAuthoringDependency = Annotated[PuzzleAuthoringService, Depends(get_puzzle_authoring_service)]


def get_content_management_service(
    session: DatabaseSession, storage: AssetStorageDependency
) -> ContentManagementService:
    return ContentManagementService(ContentRepository(session), storage)


ContentManagementDependency = Annotated[ContentManagementService, Depends(get_content_management_service)]


def get_scheduling_service(session: DatabaseSession) -> SchedulingService:
    return SchedulingService(ScheduleRepository(session))


SchedulingDependency = Annotated[SchedulingService, Depends(get_scheduling_service)]


def get_gameplay_service(session: DatabaseSession) -> GameplayService:
    return GameplayService(GameRepository(session), settings.game_timezone)


GameplayDependency = Annotated[GameplayService, Depends(get_gameplay_service)]


def get_guest_tokens() -> GuestTokenManager:
    return GuestTokenManager(settings.guest_cookie_secret)


GuestTokenDependency = Annotated[GuestTokenManager, Depends(get_guest_tokens)]


def get_albumnesia_game_service(session: DatabaseSession) -> AlbumnesiaGameService:
    return AlbumnesiaGameService(
        AlbumnesiaGameRepository(session), settings.game_timezone,
        settings.guest_cookie_secret, settings.albumnesia_room_ttl_days,
    )


AlbumnesiaGameDependency = Annotated[AlbumnesiaGameService, Depends(get_albumnesia_game_service)]

def get_badly_game_service(session: DatabaseSession) -> BadlyGameService:
    return BadlyGameService(BadlyGameRepository(session), settings.game_timezone, settings.guest_cookie_secret, settings.albumnesia_room_ttl_days)

BadlyGameDependency = Annotated[BadlyGameService, Depends(get_badly_game_service)]
