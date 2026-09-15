import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


HintState = Literal["locked", "available", "used"]


class StartGameRequest(BaseModel):
    category: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class GameStateRead(BaseModel):
    session_id: uuid.UUID
    category: str
    status: str
    current_round: int
    maximum_rounds: int
    reveal_duration_ms: int
    reveal_radius_percent: Decimal | None
    show_full_image: bool
    hints_available: bool
    cryptic_hint_state: HintState
    title_pattern_hint_state: HintState
    image_url: str
    glimpse_consumed: bool
    guess_available_at: datetime | None
    score_estimate: Decimal
    score_scale: Decimal
    time_penalty_per_second: Decimal
    cryptic_hint_penalty: Decimal
    title_pattern_hint_penalty: Decimal


class GlimpseRead(BaseModel):
    round_number: int
    countdown_ms: int
    duration_ms: int
    radius_percent: Decimal | None
    show_full_image: bool
    reveal_x: Decimal | None = None
    reveal_y: Decimal | None = None
    image_url: str


class GuessRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class GuessOutcome(BaseModel):
    correct: bool
    applied_wrong_guess_penalty: Decimal
    raw_applied_wrong_guess_penalty: Decimal
    state: GameStateRead | None = None
    result: "GameResultRead | None" = None


class HintRead(BaseModel):
    kind: Literal["cryptic", "title-pattern"]
    value: str
    penalty: Decimal
    newly_unlocked: bool


class GuessResultRead(BaseModel):
    round_number: int
    submitted_title: str
    response_time_ms: int
    applied_wrong_guess_penalty: Decimal
    raw_applied_wrong_guess_penalty: Decimal
    hints_used_count: int


class GameResultRead(BaseModel):
    status: Literal["won", "lost"]
    canonical_movie_title: str
    final_score: Decimal
    raw_final_score: Decimal
    raw_score_scale: Decimal
    score_scale: Decimal
    solved_round: int | None
    wrong_guesses: list[GuessResultRead]
    active_guess_ms: int
    cryptic_hint_used: bool
    title_pattern_used: bool
    total_hint_penalty: Decimal
    time_penalty: Decimal
    full_image_url: str
    message: str | None = None


GuessOutcome.model_rebuild()
