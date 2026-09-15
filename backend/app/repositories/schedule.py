from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.app.models.entities import Category, DailyPuzzle, Puzzle, RuleSet


class ScheduleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def options():
        return (joinedload(DailyPuzzle.puzzle).joinedload(Puzzle.movie), joinedload(DailyPuzzle.category), joinedload(DailyPuzzle.rule_set))

    def list(self) -> list[DailyPuzzle]:
        return list(self.session.scalars(select(DailyPuzzle).options(*self.options()).order_by(DailyPuzzle.puzzle_date, DailyPuzzle.category_id)))

    def get(self, schedule_id: uuid.UUID, lock: bool = False) -> DailyPuzzle | None:
        statement = select(DailyPuzzle).where(DailyPuzzle.id == schedule_id).options(*self.options())
        if lock:
            statement = statement.with_for_update(of=DailyPuzzle)
        return self.session.scalar(statement)

    def get_puzzle(self, puzzle_id: uuid.UUID) -> Puzzle | None:
        return self.session.get(Puzzle, puzzle_id)

    def get_category(self, category_id: uuid.UUID) -> Category | None:
        return self.session.get(Category, category_id)

    def get_rule_set(self, rule_set_id: uuid.UUID) -> RuleSet | None:
        return self.session.get(RuleSet, rule_set_id)

    def default_rule_set(self) -> RuleSet | None:
        return self.session.scalar(select(RuleSet).where(RuleSet.name == "Daily gameplay v2"))

    def ready_puzzles(self) -> list[Puzzle]:
        return list(self.session.scalars(select(Puzzle).where(Puzzle.status == "ready").options(joinedload(Puzzle.movie)).order_by(Puzzle.created_at)))

    def playable_categories(self) -> list[Category]:
        return list(self.session.scalars(select(Category).where(Category.is_playable.is_(True), Category.is_active.is_(True)).order_by(Category.name)))

    def rule_sets(self) -> list[RuleSet]:
        return list(self.session.scalars(select(RuleSet).order_by(RuleSet.created_at.desc())))
