from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from backend.app.models.entities import AlbumnesiaContent, BadlyExplainedContent, ContentEntry
from backend.app.repositories.content import ContentRepository, normalized_answer
from backend.app.schemas.content import AlbumnesiaPatch, AlbumnesiaWrite, BadlyExplainedPatch, BadlyExplainedWrite
from backend.app.storage import LocalFilesystemStorage


class ContentValidationError(ValueError): pass
class ContentConflictError(ValueError): pass
class ContentNotFoundError(LookupError): pass


def serialize_regions(regions) -> list[dict]:
    """Store normalized mask coordinates as JSON numbers, not Decimal strings."""
    serialized = []
    for region in regions:
        kind = region["kind"] if isinstance(region, dict) else region.kind
        points = region["points"] if isinstance(region, dict) else region.points
        serialized.append({
            "kind": kind,
            "points": [
                {
                    "x": float(point["x"] if isinstance(point, dict) else point.x),
                    "y": float(point["y"] if isinstance(point, dict) else point.y),
                }
                for point in points
            ],
        })
    return serialized


class ContentManagementService:
    def __init__(self, repository: ContentRepository, storage: LocalFilesystemStorage) -> None:
        self.repository, self.session, self.storage = repository, repository.session, storage

    @staticmethod
    def validate_answers(primary: str, alternatives: list[str]) -> None:
        values = [normalized_answer(value) for value in [primary, *alternatives]]
        if any(not value for value in values):
            raise ContentValidationError("Answers must contain letters or numbers")
        if len(values) != len(set(values)):
            raise ContentConflictError("The primary and alternative answers must be unique")

    def ensure_answers_available(self, category: str, primary: str, alternatives: list[str], exclude_id=None) -> None:
        self.validate_answers(primary, alternatives)
        conflict = self.repository.conflicting_answer(category, [primary, *alternatives], exclude_id)
        if conflict:
            raise ContentConflictError(f'Answer already belongs to "{conflict.primary_answer}" in this category')

    def _commit_staged(self, entry: ContentEntry, stage_id: str, directory: str) -> ContentEntry:
        image_key = None
        try:
            self.storage.staged_path(stage_id)
            image_key = self.storage.finalize(stage_id, directory)
            entry.image_key = image_key
            self.session.add(entry)
            self.session.commit()
            content_id = entry.id
        except Exception as exc:
            self.session.rollback()
            if image_key: self.storage.delete(image_key)
            self.storage.delete_staged(stage_id)
            if isinstance(exc, IntegrityError):
                raise ContentConflictError("Content conflicts with an existing record") from exc
            if isinstance(exc, (ValueError, FileNotFoundError, OSError)):
                raise ContentValidationError(str(exc)) from exc
            raise
        return self.repository.get(content_id)  # type: ignore[return-value]

    def create_badly_explained(self, payload: BadlyExplainedWrite) -> ContentEntry:
        self.ensure_answers_available("badly_explained", payload.title, payload.alternative_answers)
        entry = ContentEntry(
            category="badly_explained", primary_answer=payload.title,
            alternative_answers=payload.alternative_answers, image_key="pending",
            difficulty=payload.difficulty, is_active=payload.is_active,
            badly_explained=BadlyExplainedContent(clues=list(payload.clues)),
        )
        return self._commit_staged(entry, payload.staged_upload_id, "badly-explained")

    def create_albumnesia(self, payload: AlbumnesiaWrite) -> ContentEntry:
        self.ensure_answers_available("albumnesia", payload.album_title, payload.alternative_answers)
        entry = ContentEntry(
            category="albumnesia", primary_answer=payload.album_title,
            alternative_answers=payload.alternative_answers, image_key="pending",
            difficulty=payload.difficulty, is_active=payload.is_active,
            albumnesia=AlbumnesiaContent(
                artist=payload.artist, release_year=payload.release_year,
                recognizable_track=payload.recognizable_track, artist_initials=payload.artist_initials,
                enabled_distortions=list(payload.enabled_distortions),
                text_mask_regions=serialize_regions(payload.text_mask_regions),
                subject_mask_regions=serialize_regions(payload.subject_mask_regions),
            ),
        )
        return self._commit_staged(entry, payload.staged_upload_id, "albumnesia")

    def update_badly_explained(self, content_id: uuid.UUID, payload: BadlyExplainedPatch) -> ContentEntry:
        entry = self.require(content_id, "badly_explained")
        values = payload.model_dump(exclude_unset=True)
        primary, alternatives = values.get("title", entry.primary_answer), values.get("alternative_answers", entry.alternative_answers)
        self.ensure_answers_available(entry.category, primary, alternatives, entry.id)
        if "title" in values: entry.primary_answer = values.pop("title")
        if "clues" in values: entry.badly_explained.clues = list(values.pop("clues"))
        self._apply_shared(entry, values)
        return self._save(entry)

    def update_albumnesia(self, content_id: uuid.UUID, payload: AlbumnesiaPatch) -> ContentEntry:
        entry = self.require(content_id, "albumnesia")
        values = payload.model_dump(exclude_unset=True)
        primary, alternatives = values.get("album_title", entry.primary_answer), values.get("alternative_answers", entry.alternative_answers)
        self.ensure_answers_available(entry.category, primary, alternatives, entry.id)
        if "album_title" in values: entry.primary_answer = values.pop("album_title")
        shared = {key: values.pop(key) for key in list(values) if key in {"alternative_answers", "difficulty", "is_active"}}
        enabled = values.get("enabled_distortions", entry.albumnesia.enabled_distortions)
        subject_regions = values.get("subject_mask_regions", entry.albumnesia.subject_mask_regions)
        active = shared.get("is_active", entry.is_active)
        self.validate_album_configuration(active, enabled, subject_regions)
        self._apply_shared(entry, shared)
        for name, value in values.items():
            if name in {"text_mask_regions", "subject_mask_regions"}:
                value = serialize_regions(value)
            setattr(entry.albumnesia, name, value)
        return self._save(entry)

    @staticmethod
    def validate_album_configuration(is_active: bool, enabled: list[str], subject_regions: list) -> None:
        if is_active and not enabled:
            raise ContentValidationError("An active album requires at least one enabled distortion")
        if is_active and "identity_crisis" in enabled and not subject_regions:
            raise ContentValidationError("Identity Crisis requires at least one subject region")

    @staticmethod
    def _apply_shared(entry: ContentEntry, values: dict) -> None:
        for name in ("alternative_answers", "difficulty", "is_active"):
            if name in values: setattr(entry, name, values[name])
        entry.updated_at = datetime.now(timezone.utc)

    def _save(self, entry: ContentEntry) -> ContentEntry:
        try: self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ContentConflictError("Content conflicts with an existing record") from exc
        return self.repository.get(entry.id)  # type: ignore[return-value]

    def require(self, content_id: uuid.UUID, category: str | None = None) -> ContentEntry:
        entry = self.repository.get(content_id, lock=True)
        if entry is None or (category and entry.category != category):
            raise ContentNotFoundError("Content entry not found")
        return entry

    def replace_image(self, content_id: uuid.UUID, stage_id: str) -> ContentEntry:
        entry, new_key = self.require(content_id), None
        old_key = entry.image_key
        try:
            new_key = self.storage.finalize(stage_id, entry.category.replace("_", "-"))
            entry.image_key, entry.updated_at = new_key, datetime.now(timezone.utc)
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            if new_key: self.storage.delete(new_key)
            self.storage.delete_staged(stage_id)
            raise ContentValidationError("Could not replace the content image") from exc
        if not self.repository.image_is_referenced(old_key): self.storage.delete(old_key)
        return self.repository.get(entry.id)  # type: ignore[return-value]

    def duplicate(self, content_id: uuid.UUID, primary_answer: str | None) -> ContentEntry:
        source = self.require(content_id)
        answer = (primary_answer or f"{source.primary_answer} copy").strip()
        self.ensure_answers_available(source.category, answer, [])
        copied_key = None
        try:
            copied_key = self.storage.copy(source.image_key, source.category.replace("_", "-"))
            duplicate = ContentEntry(category=source.category, primary_answer=answer, alternative_answers=[], image_key=copied_key, difficulty=source.difficulty, is_active=False)
            if source.badly_explained:
                duplicate.badly_explained = BadlyExplainedContent(clues=list(source.badly_explained.clues))
            if source.albumnesia:
                album = source.albumnesia
                duplicate.albumnesia = AlbumnesiaContent(
                    artist=album.artist, release_year=album.release_year,
                    recognizable_track=album.recognizable_track, artist_initials=album.artist_initials,
                    enabled_distortions=list(album.enabled_distortions), text_mask_regions=list(album.text_mask_regions),
                    subject_mask_regions=list(album.subject_mask_regions),
                )
            self.session.add(duplicate); self.session.commit(); duplicate_id = duplicate.id
        except Exception as exc:
            self.session.rollback()
            if copied_key: self.storage.delete(copied_key)
            if isinstance(exc, IntegrityError): raise ContentConflictError("Duplicate content could not be saved") from exc
            raise
        return self.repository.get(duplicate_id)  # type: ignore[return-value]

    def delete(self, content_id: uuid.UUID) -> bool:
        entry = self.require(content_id)
        image_key = entry.image_key
        self.session.delete(entry); self.session.commit()
        image_deleted = not self.repository.image_is_referenced(image_key)
        if image_deleted: self.storage.delete(image_key)
        return image_deleted
