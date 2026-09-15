from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class RoomCreate(BaseModel):
    room_name: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=2, max_length=40)

    @field_validator("room_name", "display_name")
    @classmethod
    def clean(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("must contain at least two characters")
        if any(character in value for character in "<>") or any(ord(character) < 32 for character in value):
            raise ValueError("contains unsupported characters")
        return value


class RoomJoin(BaseModel):
    display_name: str = Field(min_length=2, max_length=40)

    @field_validator("display_name")
    @classmethod
    def clean(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("must contain at least two characters")
        if any(character in value for character in "<>") or any(ord(character) < 32 for character in value):
            raise ValueError("contains unsupported characters")
        return value


class AnswerSubmit(BaseModel):
    title: str = Field(default="", max_length=300)


class HomeRead(BaseModel):
    daily_date: date
    active_album_count: int
    daily_available: bool
    streak: int
    completed_today: bool


class RoomRead(BaseModel):
    code: str
    name: str
    host_name: str
    status: str
    expires_at: datetime
    participant_count: int
    joined: bool
    current_player_name: str | None = None
    attempt_id: uuid.UUID | None = None


class CluesRead(BaseModel):
    artist_initials: str
    release_year: int | None
    recognizable_track: str


class RoundResultRead(BaseModel):
    round_number: int
    title: str
    artist: str
    submitted_title: str | None
    correct: bool
    score: Decimal
    answer_time_ms: int


class AttemptStateRead(BaseModel):
    attempt_id: uuid.UUID
    mode: str
    room_code: str | None = None
    status: str
    phase: str
    round_number: int
    total_rounds: int = 5
    phase_deadline: datetime | None
    server_time: datetime
    image_url: str | None = None
    distortion: str | None = None
    distortion_seed: int | None = None
    text_mask_regions: list[dict] | None = None
    subject_mask_regions: list[dict] | None = None
    clues: CluesRead | None = None
    revealed_title: str | None = None
    revealed_artist: str | None = None
    last_correct: bool | None = None
    last_score: Decimal | None = None
    correct_count: int
    total_score: Decimal
    max_score: Decimal = Decimal("50.00")
    legacy_score: bool = False
    streak: int = 0
    results: list[RoundResultRead] | None = None


class LeaderboardEntryRead(BaseModel):
    display_name: str
    finished: bool
    correct_count: int | None = None
    score: Decimal | None = None
    answer_time_ms: int | None = None
    average_response_ms: int | None = None
    completed_at: datetime | None = None
    is_current: bool = False


class LeaderboardRead(BaseModel):
    code: str
    room_name: str
    entries: list[LeaderboardEntryRead]
