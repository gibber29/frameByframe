import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    Category,
    DailyPuzzle,
    GameSession,
    Guess,
    PublicationStatus,
    PuzzleMessage,
    RuleSetWrongGuessPenalty,
    SessionEvent,
)


class GameRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def published_daily(self, category_slug: str, puzzle_date: date, now: datetime) -> DailyPuzzle | None:
        return self.session.scalar(
            select(DailyPuzzle)
            .join(DailyPuzzle.category)
            .where(
                Category.slug == category_slug,
                Category.is_playable.is_(True),
                Category.is_active.is_(True),
                DailyPuzzle.puzzle_date == puzzle_date,
                DailyPuzzle.status == PublicationStatus.PUBLISHED,
                (DailyPuzzle.publish_at.is_(None) | (DailyPuzzle.publish_at <= now)),
                (DailyPuzzle.close_at.is_(None) | (DailyPuzzle.close_at > now)),
            )
        )

    def find_guest_session(self, daily_puzzle_id: uuid.UUID, guest_id: uuid.UUID) -> GameSession | None:
        return self.session.scalar(
            select(GameSession).where(
                GameSession.daily_puzzle_id == daily_puzzle_id,
                GameSession.guest_id == guest_id,
            )
        )

    def get_session(self, session_id: uuid.UUID, guest_id: uuid.UUID, lock: bool = False) -> GameSession | None:
        statement = select(GameSession).where(GameSession.id == session_id, GameSession.guest_id == guest_id)
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def glimpse_exists(self, session_id: uuid.UUID, round_number: int) -> bool:
        return self.session.scalar(
            select(SessionEvent.id).where(
                SessionEvent.session_id == session_id,
                SessionEvent.round_number == round_number,
                SessionEvent.event_type == "glimpse_shown",
            ).limit(1)
        ) is not None

    def wrong_penalty(self, rule_set_id: uuid.UUID, round_number: int, hints_used_count: int):
        penalty = self.session.scalar(
            select(RuleSetWrongGuessPenalty.penalty_amount).where(
                RuleSetWrongGuessPenalty.rule_set_id == rule_set_id,
                RuleSetWrongGuessPenalty.round_number == round_number,
                RuleSetWrongGuessPenalty.hints_used_count == hints_used_count,
            )
        )
        if penalty is None:
            raise LookupError("The scheduled rule set has no penalty for this round and hint state")
        return penalty

    def message(self, puzzle_id: uuid.UUID, event: str) -> str | None:
        return self.session.scalar(
            select(PuzzleMessage.message).where(
                PuzzleMessage.puzzle_id == puzzle_id,
                PuzzleMessage.event == event,
                PuzzleMessage.is_active.is_(True),
            ).order_by(PuzzleMessage.priority.desc()).limit(1)
        )
