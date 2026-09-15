import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.models.entities import ContentStatus, DailyPuzzle, PublicationStatus
from backend.app.repositories.schedule import ScheduleRepository
from backend.app.schemas.schedule import SchedulePatch, ScheduleWrite


class ScheduleError(ValueError):
    pass


class ScheduleConflict(ScheduleError):
    pass


class ScheduleNotFound(LookupError):
    pass


class SchedulingService:
    def __init__(self, repository: ScheduleRepository) -> None:
        self.repository = repository
        self.session = repository.session

    def validate(self, values: dict) -> None:
        puzzle = self.repository.get_puzzle(values["puzzle_id"])
        if puzzle is None:
            raise ScheduleError("Puzzle does not exist")
        category = self.repository.get_category(values["category_id"])
        if category is None or not category.is_playable or not category.is_active:
            raise ScheduleError("Daily puzzles require an active playable category")
        if self.repository.get_rule_set(values["rule_set_id"]) is None:
            raise ScheduleError("Rule set does not exist")
        if values["status"] in {PublicationStatus.SCHEDULED, PublicationStatus.PUBLISHED} and puzzle.status != ContentStatus.READY:
            raise ScheduleError("Only ready puzzles may be scheduled or published")
        if values.get("publish_at") and values.get("close_at") and values["close_at"] <= values["publish_at"]:
            raise ScheduleError("close_at must be after publish_at")

    def create(self, payload: ScheduleWrite) -> DailyPuzzle:
        values = payload.model_dump()
        if values["rule_set_id"] is None:
            default_rules = self.repository.default_rule_set()
            if default_rules is None:
                raise ScheduleError("Default rule set Daily gameplay v2 does not exist")
            values["rule_set_id"] = default_rules.id
        self.validate(values)
        schedule = DailyPuzzle(**values)
        self.session.add(schedule)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ScheduleConflict("An active schedule already exists for this category and date") from exc
        return self.repository.get(schedule.id)  # type: ignore[return-value]

    def update(self, schedule_id: uuid.UUID, payload: SchedulePatch) -> DailyPuzzle:
        schedule = self.repository.get(schedule_id, lock=True)
        if schedule is None:
            raise ScheduleNotFound("Schedule not found")
        changes = payload.model_dump(exclude_unset=True)
        values = {name: getattr(schedule, name) for name in (
            "puzzle_id", "category_id", "rule_set_id", "puzzle_date", "publish_at", "close_at", "status"
        )}
        values.update(changes)
        self.validate(values)
        for name, value in changes.items():
            setattr(schedule, name, value)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ScheduleConflict("An active schedule already exists for this category and date") from exc
        return self.repository.get(schedule.id)  # type: ignore[return-value]

    def delete(self, schedule_id: uuid.UUID) -> None:
        schedule = self.repository.get(schedule_id, lock=True)
        if schedule is None:
            raise ScheduleNotFound("Schedule not found")
        self.session.delete(schedule)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ScheduleConflict("A schedule with game sessions cannot be deleted") from exc
