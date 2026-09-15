import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator

from backend.app.models.entities import PublicationStatus


class ScheduleWrite(BaseModel):
    puzzle_id: uuid.UUID
    category_id: uuid.UUID
    rule_set_id: uuid.UUID | None = None
    puzzle_date: date
    publish_at: datetime | None = None
    close_at: datetime | None = None
    status: PublicationStatus = PublicationStatus.SCHEDULED

    @model_validator(mode="after")
    def window_is_valid(self) -> "ScheduleWrite":
        if self.publish_at and self.close_at and self.close_at <= self.publish_at:
            raise ValueError("close_at must be after publish_at")
        return self


class SchedulePatch(BaseModel):
    puzzle_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    rule_set_id: uuid.UUID | None = None
    puzzle_date: date | None = None
    publish_at: datetime | None = None
    close_at: datetime | None = None
    status: PublicationStatus | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_cleared(self) -> "SchedulePatch":
        required = ("puzzle_id", "category_id", "rule_set_id", "puzzle_date", "status")
        for field_name in required:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if self.publish_at and self.close_at and self.close_at <= self.publish_at:
            raise ValueError("close_at must be after publish_at")
        return self


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    puzzle_id: uuid.UUID
    puzzle_title: str
    category_id: uuid.UUID
    category_name: str
    category_slug: str
    rule_set_id: uuid.UUID
    rule_set_name: str
    puzzle_date: date
    publish_at: datetime | None
    close_at: datetime | None
    status: PublicationStatus


class ScheduleOptions(BaseModel):
    ready_puzzles: list[dict]
    playable_categories: list[dict]
    rule_sets: list[dict]
    schedules: list[ScheduleRead]
