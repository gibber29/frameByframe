import uuid

from fastapi import APIRouter, Cookie, HTTPException, Query, Response
from fastapi.responses import FileResponse

from backend.app.api.dependencies import AlbumnesiaGameDependency, AssetStorageDependency, GuestTokenDependency
from backend.app.core.config import settings
from backend.app.schemas.albumnesia_game import (
    AnswerSubmit, AttemptStateRead, HomeRead, LeaderboardRead, RoomCreate, RoomJoin, RoomRead,
)
from backend.app.services.albumnesia_game import AlbumnesiaConflict, AlbumnesiaNotFound

router = APIRouter(prefix="/albumnesia", tags=["albumnesia"])
COOKIE_NAME = "framebyframe_guest"


def fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, AlbumnesiaNotFound) else 409, detail=str(exc))


def identity(token: str | None, response: Response, tokens: GuestTokenDependency):
    result = tokens.resolve(token)
    if result.is_new:
        response.set_cookie(COOKIE_NAME, result.token, httponly=True, secure=settings.guest_cookie_secure,
                            samesite="lax", max_age=60 * 60 * 24 * 400)
    return result


def room_read(room, guest_id: uuid.UUID, service) -> dict:
    participant = service.repository.participant(room.id, guest_id)
    attempt = next(iter(participant.attempts), None) if participant else None
    return {"code": str(room.code).upper(), "name": room.name, "expires_at": room.expires_at,
            "host_name": room.host_display_name, "status": room.status,
            "participant_count": len(room.participants), "joined": participant is not None,
            "current_player_name": participant.display_name if participant else None,
            "attempt_id": attempt.id if attempt else None}


@router.get("/home", response_model=HomeRead)
def home(response: Response, service: AlbumnesiaGameDependency, tokens: GuestTokenDependency,
         framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    guest = identity(framebyframe_guest, response, tokens)
    return service.home(guest.id)


@router.get("/titles", response_model=list[str])
def titles(service: AlbumnesiaGameDependency, q: str | None = Query(default=None, max_length=200),
           limit: int = Query(default=30, ge=1, le=100)) -> list[str]:
    return service.titles(q, limit)


@router.post("/daily/start", response_model=AttemptStateRead)
def daily_start(response: Response, service: AlbumnesiaGameDependency, tokens: GuestTokenDependency,
                framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    guest = identity(framebyframe_guest, response, tokens)
    try:
        return service.state(service.start_daily(guest.id))
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


@router.post("/rooms", response_model=RoomRead, status_code=201)
def create_room(payload: RoomCreate, response: Response, service: AlbumnesiaGameDependency,
                tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    guest = identity(framebyframe_guest, response, tokens)
    try:
        room = service.create_room(payload.room_name, payload.display_name, guest.id)
        return room_read(room, guest.id, service)
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


@router.get("/rooms/{code}", response_model=RoomRead)
def get_room(code: str, response: Response, service: AlbumnesiaGameDependency,
             tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    guest = identity(framebyframe_guest, response, tokens)
    try:
        return room_read(service.get_room(code), guest.id, service)
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


@router.post("/rooms/{code}/join", response_model=RoomRead)
def join_room(code: str, payload: RoomJoin, response: Response, service: AlbumnesiaGameDependency,
              tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    guest = identity(framebyframe_guest, response, tokens)
    try:
        room = service.join_room(code, payload.display_name, guest.id)
        return room_read(room, guest.id, service)
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


@router.post("/rooms/{code}/continue", response_model=AttemptStateRead)
def continue_room(code: str, response: Response, service: AlbumnesiaGameDependency,
                  tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    guest = identity(framebyframe_guest, response, tokens)
    try:
        return service.state(service.continue_room(code, guest.id))
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


@router.get("/rooms/{code}/leaderboard", response_model=LeaderboardRead)
def leaderboard(code: str, service: AlbumnesiaGameDependency, tokens: GuestTokenDependency,
                framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    try:
        room = service.get_room(code)
        guest = tokens.resolve(framebyframe_guest)
        return {"code": str(room.code).upper(), "room_name": room.name,
                "entries": service.leaderboard(room, None if guest.is_new else guest.id)}
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


def owned(attempt_id: uuid.UUID, token: str | None, service, tokens):
    guest = tokens.resolve(token)
    if guest.is_new:
        raise AlbumnesiaNotFound("Game attempt not found")
    return service.require_attempt(attempt_id, guest.id)


@router.get("/attempts/{attempt_id}", response_model=AttemptStateRead)
def attempt_state(attempt_id: uuid.UUID, service: AlbumnesiaGameDependency, tokens: GuestTokenDependency,
                  framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    try:
        return service.state(owned(attempt_id, framebyframe_guest, service, tokens))
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


@router.post("/attempts/{attempt_id}/ready", response_model=AttemptStateRead)
def ready(attempt_id: uuid.UUID, service: AlbumnesiaGameDependency, tokens: GuestTokenDependency,
          framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    try:
        guest = tokens.resolve(framebyframe_guest)
        if guest.is_new:
            raise AlbumnesiaNotFound("Game attempt not found")
        return service.state(service.ready(attempt_id, guest.id))
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptStateRead)
def submit(attempt_id: uuid.UUID, payload: AnswerSubmit, service: AlbumnesiaGameDependency,
           tokens: GuestTokenDependency, framebyframe_guest: str | None = Cookie(default=None)) -> dict:
    try:
        guest = tokens.resolve(framebyframe_guest)
        if guest.is_new:
            raise AlbumnesiaNotFound("Game attempt not found")
        return service.state(service.submit(attempt_id, guest.id, payload.title))
    except (AlbumnesiaConflict, AlbumnesiaNotFound) as exc:
        raise fail(exc) from exc


@router.get("/attempts/{attempt_id}/image")
def image(attempt_id: uuid.UUID, service: AlbumnesiaGameDependency, tokens: GuestTokenDependency,
          storage: AssetStorageDependency, framebyframe_guest: str | None = Cookie(default=None)) -> FileResponse:
    try:
        attempt = service.synchronize(owned(attempt_id, framebyframe_guest, service, tokens))
        if attempt.phase not in {"ready", "memorize"}:
            raise AlbumnesiaNotFound("Cover is not available during this phase")
        path = storage.resolve(service._round(attempt).image_key_snapshot)
    except (AlbumnesiaConflict, AlbumnesiaNotFound, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Album cover not found") from exc
    return FileResponse(path, media_type=storage.media_type(path), headers={"Cache-Control": "private, no-store"})
