from __future__ import annotations

import unicodedata
import uuid

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, joinedload

from backend.app.models.entities import AlbumnesiaContent, AlbumnesiaGameRound, ContentEntry, Puzzle


def normalized_answer(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in value if character.isalnum())


class ContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def options():
        return (joinedload(ContentEntry.badly_explained), joinedload(ContentEntry.albumnesia))

    def list(
        self, search: str | None = None, category: str | None = None,
        difficulty: int | None = None, is_active: bool | None = None,
    ) -> list[ContentEntry]:
        statement = select(ContentEntry).options(*self.options())
        if search:
            term = f"%{search.strip()}%"
            statement = statement.outerjoin(ContentEntry.albumnesia).where(or_(
                ContentEntry.primary_answer.ilike(term),
                cast(ContentEntry.alternative_answers, String).ilike(term),
                AlbumnesiaContent.artist.ilike(term),
            ))
        if category:
            statement = statement.where(ContentEntry.category == category)
        if difficulty is not None:
            statement = statement.where(ContentEntry.difficulty == difficulty)
        if is_active is not None:
            statement = statement.where(ContentEntry.is_active == is_active)
        return list(self.session.scalars(statement.order_by(ContentEntry.created_at.desc())))

    def get(self, content_id: uuid.UUID, lock: bool = False) -> ContentEntry | None:
        statement = select(ContentEntry).where(ContentEntry.id == content_id).options(*self.options())
        if lock:
            statement = statement.with_for_update(of=ContentEntry)
        return self.session.scalar(statement)

    def conflicting_answer(
        self, category: str, answers: list[str], exclude_id: uuid.UUID | None = None
    ) -> ContentEntry | None:
        requested = {normalized_answer(answer) for answer in answers}
        statement = select(ContentEntry).where(ContentEntry.category == category)
        if exclude_id:
            statement = statement.where(ContentEntry.id != exclude_id)
        for entry in self.session.scalars(statement):
            existing = {normalized_answer(entry.primary_answer)} | {
                normalized_answer(answer) for answer in entry.alternative_answers
            }
            if requested & existing:
                return entry
        return None

    def image_is_referenced(self, image_key: str) -> bool:
        content_count = self.session.scalar(select(func.count()).select_from(ContentEntry).where(ContentEntry.image_key == image_key))
        puzzle_count = self.session.scalar(select(func.count()).select_from(Puzzle).where(Puzzle.image_key == image_key))
        game_count = self.session.scalar(select(func.count()).select_from(AlbumnesiaGameRound).where(AlbumnesiaGameRound.image_key_snapshot == image_key))
        return bool(content_count or puzzle_count or game_count)
