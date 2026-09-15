import uuid

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import FileResponse

from backend.app.api.dependencies import AssetStorageDependency, GameplayDependency, GuestTokenDependency
from backend.app.core.config import settings
from backend.app.schemas.game import GameResultRead, GameStateRead, GlimpseRead, GuessOutcome, GuessRequest, HintRead, StartGameRequest
from backend.app.services.gameplay import GameConflict, GameNotFound
from backend.app.services.puzzle_authoring import movie_directory

router = APIRouter(prefix="/game", tags=["game"])
COOKIE_NAME = "framebyframe_guest"


def error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, GameNotFound) else 409, detail=str(exc))


def guest_id(token: str | None, tokens: GuestTokenDependency) -> uuid.UUID:
    identity = tokens.resolve(token)
    if identity.is_new:
        raise GameNotFound("A valid guest identifier is required")
    return identity.id


@router.get("/categories")
def game_categories(service: GameplayDependency) -> list[dict]:
    now = service.now()
    today = now.astimezone(service.timezone).date()
    from backend.app.models.entities import Category, DailyPuzzle, PublicationStatus
    from sqlalchemy import select

    rows = service.session.execute(
        select(Category.slug, Category.name)
        .join(DailyPuzzle, DailyPuzzle.category_id == Category.id)
        .where(
            Category.is_playable.is_(True), Category.is_active.is_(True),
            DailyPuzzle.puzzle_date == today, DailyPuzzle.status == PublicationStatus.PUBLISHED,
            (DailyPuzzle.publish_at.is_(None) | (DailyPuzzle.publish_at <= now)),
            (DailyPuzzle.close_at.is_(None) | (DailyPuzzle.close_at > now)),
        ).order_by(Category.name)
    ).all()
    return [{"slug": slug, "name": name} for slug, name in rows]


@router.post("/start", response_model=GameStateRead)
def start_game(
    payload: StartGameRequest,
    response: Response,
    service: GameplayDependency,
    tokens: GuestTokenDependency,
    framebyframe_guest: str | None = Cookie(default=None),
) -> GameStateRead:
    identity = tokens.resolve(framebyframe_guest)
    try:
        game = service.start(payload.category, identity.id)
    except (GameNotFound, GameConflict) as exc:
        raise error(exc) from exc
    if identity.is_new:
        response.set_cookie(
            COOKIE_NAME, identity.token, httponly=True, secure=settings.guest_cookie_secure,
            samesite="lax", max_age=60 * 60 * 24 * 400,
        )
    return service.state(game)


@router.post("/{session_id}/glimpse", response_model=GlimpseRead)
def glimpse(session_id: uuid.UUID, service: GameplayDependency, tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> GlimpseRead:
    try:
        return service.glimpse(session_id, guest_id(framebyframe_guest, tokens))
    except (GameNotFound, GameConflict) as exc:
        raise error(exc) from exc


@router.post("/{session_id}/guess", response_model=GuessOutcome)
def guess(session_id: uuid.UUID, payload: GuessRequest, service: GameplayDependency, tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> GuessOutcome:
    try:
        return service.guess(session_id, guest_id(framebyframe_guest, tokens), payload.title)
    except (GameNotFound, GameConflict, LookupError) as exc:
        raise error(exc) from exc


@router.post("/{session_id}/hints/cryptic", response_model=HintRead)
def cryptic_hint(session_id: uuid.UUID, service: GameplayDependency, tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> HintRead:
    try:
        return service.unlock_cryptic(session_id, guest_id(framebyframe_guest, tokens))
    except (GameNotFound, GameConflict) as exc:
        raise error(exc) from exc


@router.post("/{session_id}/hints/title-pattern", response_model=HintRead)
def pattern_hint(session_id: uuid.UUID, service: GameplayDependency, tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> HintRead:
    try:
        return service.unlock_title_pattern(session_id, guest_id(framebyframe_guest, tokens))
    except (GameNotFound, GameConflict) as exc:
        raise error(exc) from exc


@router.get("/{session_id}/state", response_model=GameStateRead)
def game_state(session_id: uuid.UUID, service: GameplayDependency, tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> GameStateRead:
    try:
        return service.state(service.require_game(session_id, guest_id(framebyframe_guest, tokens)))
    except (GameNotFound, GameConflict) as exc:
        raise error(exc) from exc


@router.get("/{session_id}/result", response_model=GameResultRead)
def game_result(session_id: uuid.UUID, service: GameplayDependency, tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> GameResultRead:
    try:
        return service.result(service.require_game(session_id, guest_id(framebyframe_guest, tokens)))
    except (GameNotFound, GameConflict) as exc:
        raise error(exc) from exc


@router.get("/{session_id}/image")
def game_image(session_id: uuid.UUID, service: GameplayDependency, tokens: GuestTokenDependency, storage: AssetStorageDependency, framebyframe_guest: str | None = Cookie(default=None)) -> FileResponse:
    try:
        game = service.require_game(session_id, guest_id(framebyframe_guest, tokens))
        puzzle = game.daily_puzzle.puzzle
        path = storage.resolve(puzzle.image_key, movie_directory(puzzle.movie))
    except (GameNotFound, GameConflict, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Game image not found") from exc
    return FileResponse(path, media_type=storage.media_type(path), headers={"Cache-Control": "private, no-store"})
