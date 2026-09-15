import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse

from backend.app.api.dependencies import AdminMutation, AssetStorageDependency, DatabaseSession, PuzzleAuthoringDependency, SchedulingDependency
from backend.app.api.v1.routes.content import router as content_router
from backend.app.repositories.puzzles import PuzzleRepository
from backend.app.schemas.admin import (
    AssetCatalogRead,
    AssetRead,
    ClassificationCatalogRead,
    ClassificationRead,
    CompletePuzzleWrite,
    PuzzlePatch,
    PuzzleRead,
    PuzzleStageRegionRead,
    PuzzleWrite,
    RevealProfileRead,
    RevealStageRead,
    ReplaceImageWrite,
    StagedUploadRead,
    TagWrite,
)
from backend.app.schemas.schedule import ScheduleOptions, SchedulePatch, ScheduleRead, ScheduleWrite
from backend.app.repositories.schedule import ScheduleRepository
from backend.app.services.scheduling import ScheduleConflict, ScheduleError, ScheduleNotFound
from backend.app.services.puzzle_authoring import (
    AuthoringConflictError,
    AuthoringNotFoundError,
    AuthoringValidationError,
    SELECTED_HINTS,
    movie_directory,
)
from backend.app.core.config import settings
from backend.app.storage import (
    AssetNotFoundError, InvalidAssetPathError, InvalidImageError, UploadTooLargeError,
)

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(content_router)
_upload_windows: dict[str, deque[float]] = defaultdict(deque)


def enforce_upload_rate(request: Request) -> None:
    address = request.client.host if request.client else "local"
    now = time.monotonic()
    window = _upload_windows[address]
    while window and now - window[0] >= 60:
        window.popleft()
    if len(window) >= settings.upload_rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Upload rate limit exceeded")
    window.append(now)


def schedule_read(schedule) -> ScheduleRead:
    return ScheduleRead(
        id=schedule.id, puzzle_id=schedule.puzzle_id, puzzle_title=schedule.puzzle.movie.title,
        category_id=schedule.category_id, category_name=schedule.category.name,
        category_slug=schedule.category.slug, rule_set_id=schedule.rule_set_id,
        rule_set_name=schedule.rule_set.name, puzzle_date=schedule.puzzle_date,
        publish_at=schedule.publish_at, close_at=schedule.close_at, status=schedule.status,
    )


def schedule_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ScheduleNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ScheduleConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


def puzzle_read(puzzle) -> PuzzleRead:
    stages = sorted(puzzle.reveal_profile.stages, key=lambda stage: stage.round_number)
    return PuzzleRead(
        id=puzzle.id,
        movie_id=puzzle.movie_id,
        movie_title=puzzle.movie.title,
        image_key=puzzle.image_key,
        stage_regions=[PuzzleStageRegionRead.model_validate(region) for region in puzzle.stage_regions],
        cryptic_hint=puzzle.cryptic_hint,
        difficulty=puzzle.difficulty,
        reveal_profile_id=puzzle.reveal_profile_id,
        reveal_profile_name=puzzle.reveal_profile.name,
        reveal_stages=[RevealStageRead.model_validate(stage, from_attributes=True) for stage in stages],
        status=puzzle.status,
        image_url=f"/api/v1/admin/puzzles/{puzzle.id}/image",
        category_ids=[item.category_id for item in puzzle.puzzle_categories if item.category.is_playable],
        tag_ids=[item.category_id for item in puzzle.movie.movie_categories if not item.category.is_playable],
    )


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthoringConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, AuthoringNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get("/assets", response_model=None)
def list_assets(
    session: DatabaseSession,
    storage: AssetStorageDependency,
    asset_id: str | None = Query(default=None),
):
    if asset_id is not None:
        try:
            _, path = storage.resolve_asset_id(asset_id)
        except AssetNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, media_type=storage.media_type(path), headers={"Cache-Control": "no-store"})

    repository = PuzzleRepository(session)
    movies_by_directory = {movie_directory(movie): movie for movie in repository.list_movies()}
    assets = []
    for asset in storage.discover():
        movie = movies_by_directory.get(asset.movie_directory)
        if movie is not None:
            assets.append(AssetRead(
                asset_id=asset.asset_id,
                movie_id=movie.id,
                movie_title=movie.title,
                image_key=asset.image_key,
                image_url=f"/api/v1/admin/assets?asset_id={asset.asset_id}",
                suggested_hint=SELECTED_HINTS.get(movie.title),
            ))
    profiles = [
        RevealProfileRead(
            id=profile.id,
            name=profile.name,
            stages=[
                RevealStageRead.model_validate(stage, from_attributes=True)
                for stage in sorted(profile.stages, key=lambda item: item.round_number)
            ],
        )
        for profile in repository.list_profiles()
    ]
    result = AssetCatalogRead(assets=assets, reveal_profiles=profiles)
    return JSONResponse(content=jsonable_encoder(result))


@router.post("/uploads", response_model=StagedUploadRead, status_code=201)
def stage_upload(
    request: Request,
    storage: AssetStorageDependency,
    _admin: AdminMutation,
    image: UploadFile = File(...),
) -> StagedUploadRead:
    enforce_upload_rate(request)
    if Path(image.filename or "").suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=422, detail="Only WebP, PNG, and JPEG uploads are supported")
    try:
        staged = storage.save_staged(
            image.file, image.filename or "upload", settings.upload_max_bytes, settings.upload_webp_quality
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except InvalidImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StagedUploadRead(
        **staged.__dict__, image_url=f"/api/v1/admin/uploads/{staged.stage_id}/image"
    )


@router.get("/uploads/{stage_id}/image")
def staged_upload_image(stage_id: str, storage: AssetStorageDependency) -> FileResponse:
    try:
        return FileResponse(storage.staged_path(stage_id), media_type="image/webp", headers={"Cache-Control": "no-store"})
    except (AssetNotFoundError, InvalidAssetPathError) as exc:
        raise HTTPException(status_code=404, detail="Staged upload not found") from exc


@router.delete("/uploads/{stage_id}", status_code=204)
def cancel_staged_upload(stage_id: str, storage: AssetStorageDependency, _admin: AdminMutation) -> None:
    try:
        storage.delete_staged(stage_id)
    except InvalidAssetPathError as exc:
        raise HTTPException(status_code=404, detail="Staged upload not found") from exc


@router.get("/classifications", response_model=ClassificationCatalogRead)
def list_classifications(service: PuzzleAuthoringDependency) -> ClassificationCatalogRead:
    playable, tags = service.classifications()
    read = lambda item: ClassificationRead(id=item.id, name=item.name, slug=item.slug, is_playable=item.is_playable)
    return ClassificationCatalogRead(
        playable_categories=[read(item) for item in playable], tags=[read(item) for item in tags]
    )


@router.post("/tags", response_model=ClassificationRead, status_code=201)
def create_tag(payload: TagWrite, service: PuzzleAuthoringDependency, _admin: AdminMutation) -> ClassificationRead:
    try:
        tag = service.create_tag(payload.name)
    except AuthoringConflictError as exc:
        raise translate_error(exc) from exc
    return ClassificationRead(id=tag.id, name=tag.name, slug=tag.slug, is_playable=tag.is_playable)


@router.get("/puzzles", response_model=list[PuzzleRead])
def list_puzzles(session: DatabaseSession) -> list[PuzzleRead]:
    return [puzzle_read(puzzle) for puzzle in PuzzleRepository(session).list()]


@router.post("/puzzles", response_model=PuzzleRead, status_code=status.HTTP_201_CREATED)
def create_puzzle(payload: PuzzleWrite, service: PuzzleAuthoringDependency, _admin: AdminMutation) -> PuzzleRead:
    try:
        return puzzle_read(service.create(payload))
    except (AuthoringValidationError, AuthoringConflictError) as exc:
        raise translate_error(exc) from exc


@router.post("/puzzles/complete", response_model=PuzzleRead, status_code=201)
def create_complete_puzzle(
    payload: CompletePuzzleWrite, service: PuzzleAuthoringDependency, _admin: AdminMutation
) -> PuzzleRead:
    try:
        return puzzle_read(service.create_complete(payload))
    except (AuthoringValidationError, AuthoringConflictError) as exc:
        raise translate_error(exc) from exc


@router.get("/puzzles/{puzzle_id}", response_model=PuzzleRead)
def get_puzzle(puzzle_id: uuid.UUID, session: DatabaseSession) -> PuzzleRead:
    puzzle = PuzzleRepository(session).get(puzzle_id)
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    return puzzle_read(puzzle)


@router.patch("/puzzles/{puzzle_id}", response_model=PuzzleRead)
def update_puzzle(
    puzzle_id: uuid.UUID, payload: PuzzlePatch, service: PuzzleAuthoringDependency, _admin: AdminMutation
) -> PuzzleRead:
    try:
        return puzzle_read(service.update(puzzle_id, payload))
    except (AuthoringValidationError, AuthoringConflictError, AuthoringNotFoundError) as exc:
        raise translate_error(exc) from exc


@router.post("/puzzles/{puzzle_id}/image", response_model=PuzzleRead)
def replace_puzzle_image(
    puzzle_id: uuid.UUID, payload: ReplaceImageWrite, service: PuzzleAuthoringDependency, _admin: AdminMutation
) -> PuzzleRead:
    try:
        return puzzle_read(service.replace_image(puzzle_id, payload.staged_upload_id))
    except (AuthoringValidationError, AuthoringNotFoundError) as exc:
        raise translate_error(exc) from exc


@router.get("/puzzles/{puzzle_id}/image")
def puzzle_image(
    puzzle_id: uuid.UUID, session: DatabaseSession, storage: AssetStorageDependency
) -> FileResponse:
    puzzle = PuzzleRepository(session).get(puzzle_id)
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    try:
        path = storage.resolve(puzzle.image_key, movie_directory(puzzle.movie))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Puzzle image not found") from exc
    return FileResponse(path, media_type=storage.media_type(path), headers={"Cache-Control": "no-store"})


@router.get("/schedule", response_model=ScheduleOptions)
def list_schedule(session: DatabaseSession) -> ScheduleOptions:
    repository = ScheduleRepository(session)
    return ScheduleOptions(
        ready_puzzles=[{"id": str(puzzle.id), "title": puzzle.movie.title} for puzzle in repository.ready_puzzles()],
        playable_categories=[{"id": str(category.id), "name": category.name, "slug": category.slug} for category in repository.playable_categories()],
        rule_sets=[{"id": str(rule.id), "name": rule.name} for rule in repository.rule_sets()],
        schedules=[schedule_read(schedule) for schedule in repository.list()],
    )


@router.post("/schedule", response_model=ScheduleRead, status_code=201)
def create_schedule(payload: ScheduleWrite, service: SchedulingDependency, _admin: AdminMutation) -> ScheduleRead:
    try:
        return schedule_read(service.create(payload))
    except (ScheduleError, ScheduleConflict) as exc:
        raise schedule_error(exc) from exc


@router.patch("/schedule/{daily_puzzle_id}", response_model=ScheduleRead)
def update_schedule(daily_puzzle_id: uuid.UUID, payload: SchedulePatch, service: SchedulingDependency, _admin: AdminMutation) -> ScheduleRead:
    try:
        return schedule_read(service.update(daily_puzzle_id, payload))
    except (ScheduleError, ScheduleConflict, ScheduleNotFound) as exc:
        raise schedule_error(exc) from exc


@router.delete("/schedule/{daily_puzzle_id}", status_code=204)
def delete_schedule(daily_puzzle_id: uuid.UUID, service: SchedulingDependency, _admin: AdminMutation) -> None:
    try:
        service.delete(daily_puzzle_id)
    except (ScheduleConflict, ScheduleNotFound) as exc:
        raise schedule_error(exc) from exc
