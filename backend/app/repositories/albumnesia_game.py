from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.models.entities import (
    AlbumnesiaAttempt, AlbumnesiaContent, AlbumnesiaDailyProgress,
    AlbumnesiaGameSet, AlbumnesiaParticipant, AlbumnesiaRoom, ContentEntry,
)


class AlbumnesiaGameRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def active_albums(self) -> list[ContentEntry]:
        return list(self.session.scalars(
            select(ContentEntry).join(AlbumnesiaContent)
            .options(joinedload(ContentEntry.albumnesia))
            .where(ContentEntry.category == "albumnesia", ContentEntry.is_active.is_(True))
            .order_by(ContentEntry.id)
        ))

    def daily_set(self, day: date, game_version: int = 2) -> AlbumnesiaGameSet | None:
        return self.session.scalar(
            select(AlbumnesiaGameSet).options(selectinload(AlbumnesiaGameSet.rounds))
            .where(AlbumnesiaGameSet.kind == "daily", AlbumnesiaGameSet.game_date == day,
                   AlbumnesiaGameSet.game_version == game_version)
        )

    def room(self, code: str) -> AlbumnesiaRoom | None:
        return self.session.scalar(
            select(AlbumnesiaRoom)
            .options(
                joinedload(AlbumnesiaRoom.game_set).selectinload(AlbumnesiaGameSet.rounds),
                selectinload(AlbumnesiaRoom.participants),
            ).where(AlbumnesiaRoom.code == code)
        )

    def attempt(self, attempt_id: uuid.UUID, lock: bool = False) -> AlbumnesiaAttempt | None:
        statement = (
            select(AlbumnesiaAttempt)
            .options(
                joinedload(AlbumnesiaAttempt.game_set).selectinload(AlbumnesiaGameSet.rounds),
                joinedload(AlbumnesiaAttempt.participant),
                selectinload(AlbumnesiaAttempt.submissions),
            ).where(AlbumnesiaAttempt.id == attempt_id)
        )
        if lock:
            statement = statement.with_for_update(of=AlbumnesiaAttempt)
        return self.session.scalar(statement)

    def daily_attempt(self, set_id: uuid.UUID, guest_id: uuid.UUID) -> AlbumnesiaAttempt | None:
        attempt_id = self.session.scalar(select(AlbumnesiaAttempt.id).where(
            AlbumnesiaAttempt.game_set_id == set_id, AlbumnesiaAttempt.guest_id == guest_id,
            AlbumnesiaAttempt.mode == "daily",
        ))
        return self.attempt(attempt_id) if attempt_id else None

    def participant(self, room_id: uuid.UUID, guest_id: uuid.UUID) -> AlbumnesiaParticipant | None:
        return self.session.scalar(select(AlbumnesiaParticipant).where(
            AlbumnesiaParticipant.room_id == room_id, AlbumnesiaParticipant.guest_id == guest_id,
        ))

    def progress(self, guest_id: uuid.UUID) -> AlbumnesiaDailyProgress | None:
        return self.session.get(AlbumnesiaDailyProgress, guest_id)

    def room_attempts(self, set_id: uuid.UUID) -> list[AlbumnesiaAttempt]:
        return list(self.session.scalars(
            select(AlbumnesiaAttempt).options(joinedload(AlbumnesiaAttempt.participant))
            .where(AlbumnesiaAttempt.game_set_id == set_id, AlbumnesiaAttempt.mode == "room")
        ))

    def add(self, value):
        self.session.add(value)
        return value

    def commit(self) -> None:
        self.session.commit()

    def flush(self) -> None:
        self.session.flush()
