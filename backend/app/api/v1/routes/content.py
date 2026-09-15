import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.app.api.dependencies import AdminMutation, AssetStorageDependency, ContentManagementDependency, DatabaseSession
from backend.app.repositories.content import ContentRepository
from backend.app.schemas.admin import ReplaceImageWrite
from backend.app.schemas.content import (
    AlbumnesiaPatch, AlbumnesiaWrite, BadlyExplainedPatch, BadlyExplainedWrite,
    ContentRead, DuplicateContentWrite,
)
from backend.app.services.content_management import (
    ContentConflictError, ContentNotFoundError, ContentValidationError,
)
from backend.app.storage import AssetNotFoundError, InvalidAssetPathError

router = APIRouter(prefix="/content")


def content_read(entry) -> ContentRead:
    values = dict(
        id=entry.id, category=entry.category, primary_answer=entry.primary_answer,
        alternative_answers=entry.alternative_answers,
        image_url=f"/api/v1/admin/content/{entry.id}/image",
        difficulty=entry.difficulty, is_active=entry.is_active,
        created_at=entry.created_at, updated_at=entry.updated_at,
    )
    if entry.badly_explained:
        values["clues"] = entry.badly_explained.clues
    if entry.albumnesia:
        album = entry.albumnesia
        values.update(
            artist=album.artist, release_year=album.release_year,
            recognizable_track=album.recognizable_track,
            artist_initials=album.artist_initials,
            enabled_distortions=album.enabled_distortions,
            text_mask_regions=album.text_mask_regions,
            subject_mask_regions=album.subject_mask_regions,
        )
    return ContentRead(**values)


def translated(exc: Exception) -> HTTPException:
    if isinstance(exc, ContentNotFoundError): return HTTPException(404, str(exc))
    if isinstance(exc, ContentConflictError): return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


@router.get("", response_model=list[ContentRead])
def list_content(
    session: DatabaseSession, search: str | None = None, category: str | None = None,
    difficulty: int | None = Query(default=None, ge=1, le=5), is_active: bool | None = None,
) -> list[ContentRead]:
    return [content_read(entry) for entry in ContentRepository(session).list(search, category, difficulty, is_active)]


@router.get("/check-answer")
def check_answer(category: str, answer: str, session: DatabaseSession, exclude_id: uuid.UUID | None = None):
    conflict = ContentRepository(session).conflicting_answer(category, [answer], exclude_id)
    return {"duplicate": conflict is not None, "conflicting_title": conflict.primary_answer if conflict else None}


@router.post("/badly-explained", response_model=ContentRead, status_code=201)
def create_badly(payload: BadlyExplainedWrite, service: ContentManagementDependency, _admin: AdminMutation):
    try: return content_read(service.create_badly_explained(payload))
    except (ContentConflictError, ContentValidationError) as exc: raise translated(exc) from exc


@router.post("/albumnesia", response_model=ContentRead, status_code=201)
def create_album(payload: AlbumnesiaWrite, service: ContentManagementDependency, _admin: AdminMutation):
    try: return content_read(service.create_albumnesia(payload))
    except (ContentConflictError, ContentValidationError) as exc: raise translated(exc) from exc


@router.get("/{content_id}", response_model=ContentRead)
def get_content(content_id: uuid.UUID, session: DatabaseSession):
    entry = ContentRepository(session).get(content_id)
    if entry is None: raise HTTPException(404, "Content entry not found")
    return content_read(entry)


@router.patch("/{content_id}/badly-explained", response_model=ContentRead)
def update_badly(content_id: uuid.UUID, payload: BadlyExplainedPatch, service: ContentManagementDependency, _admin: AdminMutation):
    try: return content_read(service.update_badly_explained(content_id, payload))
    except (ContentConflictError, ContentValidationError, ContentNotFoundError) as exc: raise translated(exc) from exc


@router.patch("/{content_id}/albumnesia", response_model=ContentRead)
def update_album(content_id: uuid.UUID, payload: AlbumnesiaPatch, service: ContentManagementDependency, _admin: AdminMutation):
    try: return content_read(service.update_albumnesia(content_id, payload))
    except (ContentConflictError, ContentValidationError, ContentNotFoundError) as exc: raise translated(exc) from exc


@router.post("/{content_id}/image", response_model=ContentRead)
def replace_image(content_id: uuid.UUID, payload: ReplaceImageWrite, service: ContentManagementDependency, _admin: AdminMutation):
    try: return content_read(service.replace_image(content_id, payload.staged_upload_id))
    except (ContentValidationError, ContentNotFoundError) as exc: raise translated(exc) from exc


@router.get("/{content_id}/image")
def content_image(content_id: uuid.UUID, session: DatabaseSession, storage: AssetStorageDependency):
    entry = ContentRepository(session).get(content_id)
    if entry is None: raise HTTPException(404, "Content entry not found")
    try: path = storage.resolve(entry.image_key)
    except (AssetNotFoundError, InvalidAssetPathError) as exc: raise HTTPException(404, "Content image not found") from exc
    return FileResponse(path, media_type=storage.media_type(path), headers={"Cache-Control": "private, no-store"})


@router.post("/{content_id}/duplicate", response_model=ContentRead, status_code=201)
def duplicate_content(content_id: uuid.UUID, payload: DuplicateContentWrite, service: ContentManagementDependency, _admin: AdminMutation):
    try: return content_read(service.duplicate(content_id, payload.primary_answer))
    except (ContentConflictError, ContentNotFoundError) as exc: raise translated(exc) from exc


@router.delete("/{content_id}")
def delete_content(content_id: uuid.UUID, service: ContentManagementDependency, _admin: AdminMutation):
    try: return {"deleted": True, "image_deleted": service.delete(content_id)}
    except ContentNotFoundError as exc: raise translated(exc) from exc
