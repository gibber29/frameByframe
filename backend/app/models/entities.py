from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, ENUM, UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, SCHEMA


class MediaType(str, enum.Enum):
    MOVIE = "movie"
    SERIES = "series"


class CategoryType(str, enum.Enum):
    UNIVERSE = "universe"
    GENRE = "genre"
    FORMAT = "format"
    COLLECTION = "collection"


class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"


class PublicationStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class SessionStatus(str, enum.Enum):
    PLAYING = "playing"
    WON = "won"
    LOST = "lost"
    EXPIRED = "expired"


class MessageEvent(str, enum.Enum):
    WRONG_GUESS = "wrong_guess"
    HINT_USED = "hint_used"
    SOLVED_EARLY = "solved_early"
    SOLVED_LATE = "solved_late"
    FAILED = "failed"


def pg_enum(enum_class: type[enum.Enum], name: str) -> ENUM:
    return ENUM(
        enum_class,
        name=name,
        schema=SCHEMA,
        values_callable=lambda values: [value.value for value in values],
        create_type=False,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class UpdatedTimestampMixin(TimestampMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Category(UpdatedTimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'", name="slug_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    type: Mapped[CategoryType] = mapped_column(pg_enum(CategoryType, "category_type"), nullable=False, server_default="genre")
    is_playable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    movie_categories: Mapped[list[MovieCategory]] = relationship(back_populates="category", cascade="all, delete-orphan")
    puzzle_categories: Mapped[list[PuzzleCategory]] = relationship(back_populates="category", cascade="all, delete-orphan")


class Movie(UpdatedTimestampMixin, Base):
    __tablename__ = "movies"
    __table_args__ = (
        CheckConstraint("release_year BETWEEN 1888 AND 2200", name="release_year_range"),
        CheckConstraint("btrim(title) <> ''", name="movies_title_not_blank"),
        UniqueConstraint("normalized_title", "release_year", "type", name="movies_identity_unique"),
        Index("movies_normalized_title_idx", "normalized_title"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, Computed("normalize_title(title)", persisted=True))
    release_year: Mapped[int | None] = mapped_column(SmallInteger)
    type: Mapped[MediaType] = mapped_column(pg_enum(MediaType, "media_type"), nullable=False, server_default="movie")
    status: Mapped[ContentStatus] = mapped_column(pg_enum(ContentStatus, "content_status"), nullable=False, server_default="ready")

    movie_categories: Mapped[list[MovieCategory]] = relationship(back_populates="movie", cascade="all, delete-orphan")
    puzzles: Mapped[list[Puzzle]] = relationship(back_populates="movie")


class MovieCategory(Base):
    __tablename__ = "movie_categories"
    __table_args__ = (Index("movie_categories_category_idx", "category_id", "movie_id"),)

    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.movies.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.categories.id", ondelete="CASCADE"), primary_key=True)
    movie: Mapped[Movie] = relationship(back_populates="movie_categories")
    category: Mapped[Category] = relationship(back_populates="movie_categories")


class RevealProfile(TimestampMixin, Base):
    __tablename__ = "reveal_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    stages: Mapped[list[RevealStage]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    puzzles: Mapped[list[Puzzle]] = relationship(back_populates="reveal_profile")


class RevealStage(Base):
    __tablename__ = "reveal_stages"
    __table_args__ = (
        CheckConstraint("round_number BETWEEN 1 AND 10", name="round_number_range"),
        CheckConstraint("radius_percent > 0 AND radius_percent <= 100", name="radius_percent_range"),
        CheckConstraint("duration_ms > 0 AND duration_ms <= 10000", name="duration_ms_range"),
        CheckConstraint("(show_full_image AND radius_percent IS NULL) OR (NOT show_full_image AND radius_percent IS NOT NULL)", name="full_stage_shape"),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.reveal_profiles.id", ondelete="CASCADE"), primary_key=True)
    round_number: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    radius_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    show_full_image: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    profile: Mapped[RevealProfile] = relationship(back_populates="stages")


class RuleSet(TimestampMixin, Base):
    __tablename__ = "rule_sets"
    __table_args__ = (
        CheckConstraint("base_score > 0", name="base_score_positive"),
        CheckConstraint("max_score > 0", name="max_score_positive"),
        CheckConstraint("time_penalty_per_second >= 0", name="time_penalty_nonnegative"),
        CheckConstraint("replay_penalty >= 0", name="replay_penalty_nonnegative"),
        CheckConstraint("cryptic_hint_penalty >= 0", name="cryptic_hint_penalty_nonnegative"),
        CheckConstraint("title_pattern_penalty >= 0", name="title_pattern_penalty_nonnegative"),
        CheckConstraint("minimum_correct_score >= 0", name="minimum_correct_score_nonnegative"),
        CheckConstraint("max_attempts BETWEEN 1 AND 10", name="max_attempts_range"),
        CheckConstraint("score_decimal_places BETWEEN 0 AND 2", name="score_decimal_places_range"),
        CheckConstraint("minimum_correct_score <= base_score", name="minimum_not_above_base"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    base_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="1000.00")
    max_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="1000.00")
    time_penalty_per_second: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="5")
    # Retained for historic sessions; single-glimpse rules always seed this as zero.
    replay_penalty: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="0.00")
    cryptic_hint_penalty: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="50.00")
    title_pattern_penalty: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="100.00")
    minimum_correct_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="100.00")
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="5")
    score_decimal_places: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    daily_puzzles: Mapped[list[DailyPuzzle]] = relationship(back_populates="rule_set")
    wrong_guess_penalties: Mapped[list[RuleSetWrongGuessPenalty]] = relationship(
        back_populates="rule_set", cascade="all, delete-orphan"
    )


class RuleSetWrongGuessPenalty(Base):
    __tablename__ = "rule_set_wrong_guess_penalties"
    __table_args__ = (
        CheckConstraint("round_number BETWEEN 1 AND 5", name="round_number_range"),
        CheckConstraint("hints_used_count BETWEEN 0 AND 2", name="hints_used_count_range"),
        CheckConstraint("penalty_amount >= 0", name="penalty_amount_nonnegative"),
    )
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.rule_sets.id", ondelete="CASCADE"), primary_key=True
    )
    round_number: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    hints_used_count: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    penalty_amount: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    rule_set: Mapped[RuleSet] = relationship(back_populates="wrong_guess_penalties")


class Puzzle(UpdatedTimestampMixin, Base):
    __tablename__ = "puzzles"
    __table_args__ = (
        CheckConstraint("btrim(cryptic_hint) <> ''", name="cryptic_hint_not_blank"),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="difficulty_range"),
        Index("puzzles_movie_idx", "movie_id"),
        Index("puzzles_ready_idx", "status", postgresql_where=text("status = 'ready'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.movies.id", ondelete="RESTRICT"), nullable=False)
    image_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    cryptic_hint: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="3")
    reveal_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.reveal_profiles.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[ContentStatus] = mapped_column(pg_enum(ContentStatus, "content_status"), nullable=False, server_default="draft")
    movie: Mapped[Movie] = relationship(back_populates="puzzles")
    reveal_profile: Mapped[RevealProfile] = relationship(back_populates="puzzles")
    puzzle_categories: Mapped[list[PuzzleCategory]] = relationship(back_populates="puzzle", cascade="all, delete-orphan")
    messages: Mapped[list[PuzzleMessage]] = relationship(back_populates="puzzle", cascade="all, delete-orphan")
    daily_puzzles: Mapped[list[DailyPuzzle]] = relationship(back_populates="puzzle")
    stage_regions: Mapped[list[PuzzleStageRegion]] = relationship(
        back_populates="puzzle", cascade="all, delete-orphan", order_by="PuzzleStageRegion.round_number"
    )


class PuzzleStageRegion(UpdatedTimestampMixin, Base):
    __tablename__ = "puzzle_stage_regions"
    __table_args__ = (
        CheckConstraint("round_number BETWEEN 1 AND 4", name="round_number_range"),
        CheckConstraint("reveal_x BETWEEN 0 AND 100", name="reveal_x_range"),
        CheckConstraint("reveal_y BETWEEN 0 AND 100", name="reveal_y_range"),
    )

    puzzle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.puzzles.id", ondelete="CASCADE"), primary_key=True
    )
    round_number: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    reveal_x: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    reveal_y: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    puzzle: Mapped[Puzzle] = relationship(back_populates="stage_regions")


class PuzzleCategory(Base):
    __tablename__ = "puzzle_categories"
    __table_args__ = (Index("puzzle_categories_category_idx", "category_id", "puzzle_id"),)
    puzzle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.puzzles.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.categories.id", ondelete="CASCADE"), primary_key=True)
    puzzle: Mapped[Puzzle] = relationship(back_populates="puzzle_categories")
    category: Mapped[Category] = relationship(back_populates="puzzle_categories")


class PuzzleMessage(TimestampMixin, Base):
    __tablename__ = "puzzle_messages"
    __table_args__ = (
        CheckConstraint("btrim(message) <> ''", name="message_not_blank"),
        Index("puzzle_messages_lookup_idx", "puzzle_id", "event", "is_active", text("priority DESC")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    puzzle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.puzzles.id", ondelete="CASCADE"), nullable=False)
    event: Mapped[MessageEvent] = mapped_column(pg_enum(MessageEvent, "message_event"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    expected_wrong_movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{SCHEMA}.movies.id", ondelete="SET NULL"))
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    puzzle: Mapped[Puzzle] = relationship(back_populates="messages")
    expected_wrong_movie: Mapped[Movie | None] = relationship(foreign_keys=[expected_wrong_movie_id])


class ContentEntry(UpdatedTimestampMixin, Base):
    __tablename__ = "content_entries"
    __table_args__ = (
        CheckConstraint("category IN ('badly_explained', 'albumnesia', 'guess_assemble')", name="content_category_valid"),
        CheckConstraint("btrim(primary_answer) <> ''", name="content_primary_answer_not_blank"),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="content_difficulty_range"),
        CheckConstraint("jsonb_typeof(alternative_answers) = 'array'", name="content_alternatives_array"),
        Index("content_entries_filters_idx", "category", "is_active", "difficulty"),
        Index("content_entries_answer_idx", "normalized_answer"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    primary_answer: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_answer: Mapped[str] = mapped_column(Text, Computed("normalize_title(primary_answer)", persisted=True))
    alternative_answers: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    image_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="3")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    badly_explained: Mapped[BadlyExplainedContent | None] = relationship(
        back_populates="content", cascade="all, delete-orphan", uselist=False
    )
    albumnesia: Mapped[AlbumnesiaContent | None] = relationship(
        back_populates="content", cascade="all, delete-orphan", uselist=False
    )


class BadlyExplainedContent(Base):
    __tablename__ = "badly_explained_content"
    __table_args__ = (
        CheckConstraint("jsonb_typeof(clues) = 'array' AND jsonb_array_length(clues) = 4", name="exactly_four_clues"),
    )

    content_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.content_entries.id", ondelete="CASCADE"), primary_key=True
    )
    clues: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    content: Mapped[ContentEntry] = relationship(back_populates="badly_explained")


class AlbumnesiaContent(Base):
    __tablename__ = "albumnesia_content"
    __table_args__ = (
        CheckConstraint("release_year IS NULL OR release_year BETWEEN 1888 AND 2200", name="album_release_year_range"),
        CheckConstraint("jsonb_typeof(enabled_distortions) = 'array'", name="album_distortions_array"),
        CheckConstraint(
            "enabled_distortions <@ '[\"pixel_hangover\", \"sleeve_shredder\", \"channel_damage\", \"identity_crisis\", \"outline_only\"]'::jsonb",
            name="album_distortions_allowed",
        ),
        CheckConstraint("jsonb_typeof(text_mask_regions) = 'array'", name="album_text_masks_array"),
        CheckConstraint("jsonb_typeof(subject_mask_regions) = 'array'", name="album_subject_masks_array"),
        CheckConstraint(
            "NOT jsonb_path_exists(text_mask_regions, '$[*].points[*] ? (@.x < 0 || @.x > 1 || @.y < 0 || @.y > 1)')",
            name="album_text_mask_coordinates_normalized",
        ),
        CheckConstraint(
            "NOT jsonb_path_exists(subject_mask_regions, '$[*].points[*] ? (@.x < 0 || @.x > 1 || @.y < 0 || @.y > 1)')",
            name="album_subject_mask_coordinates_normalized",
        ),
    )

    content_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.content_entries.id", ondelete="CASCADE"), primary_key=True
    )
    artist: Mapped[str] = mapped_column(Text, nullable=False)
    release_year: Mapped[int | None] = mapped_column(SmallInteger)
    recognizable_track: Mapped[str] = mapped_column(Text, nullable=False)
    artist_initials: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled_distortions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    text_mask_regions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    subject_mask_regions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    content: Mapped[ContentEntry] = relationship(back_populates="albumnesia")


class AlbumnesiaGameSet(TimestampMixin, Base):
    __tablename__ = "albumnesia_game_sets"
    __table_args__ = (
        CheckConstraint("kind IN ('daily', 'room')", name="albumnesia_set_kind_allowed"),
        CheckConstraint("(kind = 'daily' AND game_date IS NOT NULL) OR (kind = 'room' AND game_date IS NULL)", name="albumnesia_set_date_shape"),
        CheckConstraint("game_version > 0", name="albumnesia_game_version_positive"),
        Index("albumnesia_daily_set_date_version_unique", "game_date", "game_version", unique=True, postgresql_where=text("kind = 'daily'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    game_date: Mapped[date | None] = mapped_column(Date)
    game_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="2")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rounds: Mapped[list[AlbumnesiaGameRound]] = relationship(back_populates="game_set", cascade="all, delete-orphan", order_by="AlbumnesiaGameRound.round_number")
    room: Mapped[AlbumnesiaRoom | None] = relationship(back_populates="game_set", cascade="all, delete-orphan", uselist=False)
    attempts: Mapped[list[AlbumnesiaAttempt]] = relationship(back_populates="game_set", cascade="all, delete-orphan")


class AlbumnesiaGameRound(Base):
    __tablename__ = "albumnesia_game_rounds"
    __table_args__ = (
        CheckConstraint("round_number BETWEEN 1 AND 5", name="albumnesia_round_number_range"),
        CheckConstraint("distortion IN ('pixel_hangover', 'sleeve_shredder', 'channel_damage', 'identity_crisis', 'outline_only')", name="albumnesia_round_distortion_allowed"),
        Index("albumnesia_game_round_content_idx", "content_id"),
    )
    game_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.albumnesia_game_sets.id", ondelete="CASCADE"), primary_key=True)
    round_number: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    content_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{SCHEMA}.content_entries.id", ondelete="SET NULL"))
    title_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_answer_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    alternative_answers_snapshot: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    artist_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    release_year_snapshot: Mapped[int | None] = mapped_column(SmallInteger)
    recognizable_track_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    artist_initials_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    image_key_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    distortion: Mapped[str] = mapped_column(String(40), nullable=False)
    distortion_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text_mask_regions_snapshot: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    subject_mask_regions_snapshot: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    game_set: Mapped[AlbumnesiaGameSet] = relationship(back_populates="rounds")


class AlbumnesiaRoom(TimestampMixin, Base):
    __tablename__ = "albumnesia_rooms"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''", name="albumnesia_room_code_not_blank"),
        CheckConstraint("btrim(name) <> ''", name="albumnesia_room_name_not_blank"),
        CheckConstraint("btrim(host_display_name) <> ''", name="albumnesia_host_name_not_blank"),
        CheckConstraint("status IN ('open', 'expired')", name="albumnesia_room_status_allowed"),
        Index("albumnesia_rooms_expiry_idx", "expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    game_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.albumnesia_game_sets.id", ondelete="CASCADE"), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    host_display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    allow_retries: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    game_set: Mapped[AlbumnesiaGameSet] = relationship(back_populates="room")
    participants: Mapped[list[AlbumnesiaParticipant]] = relationship(back_populates="room", cascade="all, delete-orphan")


class AlbumnesiaParticipant(TimestampMixin, Base):
    __tablename__ = "albumnesia_participants"
    __table_args__ = (
        CheckConstraint("btrim(display_name) <> ''", name="albumnesia_display_name_not_blank"),
        UniqueConstraint("room_id", "guest_id", name="albumnesia_one_participant_per_guest"),
        Index("albumnesia_participants_room_idx", "room_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.albumnesia_rooms.id", ondelete="CASCADE"), nullable=False)
    guest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    room: Mapped[AlbumnesiaRoom] = relationship(back_populates="participants")
    attempts: Mapped[list[AlbumnesiaAttempt]] = relationship(back_populates="participant", cascade="all, delete-orphan")


class AlbumnesiaAttempt(UpdatedTimestampMixin, Base):
    __tablename__ = "albumnesia_attempts"
    __table_args__ = (
        CheckConstraint("mode IN ('daily', 'room')", name="albumnesia_attempt_mode_allowed"),
        CheckConstraint("status IN ('playing', 'completed', 'expired')", name="albumnesia_attempt_status_allowed"),
        CheckConstraint("phase IN ('ready', 'memorize', 'guess', 'feedback', 'results')", name="albumnesia_attempt_phase_allowed"),
        CheckConstraint("current_round BETWEEN 1 AND 5", name="albumnesia_attempt_round_range"),
        CheckConstraint("correct_count BETWEEN 0 AND 5", name="albumnesia_correct_count_range"),
        CheckConstraint("score_scale IN (10.00, 50.00, 250.00)", name="albumnesia_score_scale_allowed"),
        CheckConstraint("total_score BETWEEN 0 AND score_scale", name="albumnesia_total_score_range"),
        CheckConstraint("total_answer_ms >= 0", name="albumnesia_total_answer_ms_nonnegative"),
        Index("albumnesia_daily_attempt_unique", "game_set_id", "guest_id", unique=True, postgresql_where=text("mode = 'daily'")),
        Index("albumnesia_room_attempt_unique", "participant_id", unique=True, postgresql_where=text("mode = 'room'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    game_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.albumnesia_game_sets.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{SCHEMA}.albumnesia_participants.id", ondelete="CASCADE"))
    guest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="playing")
    current_round: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    phase: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ready")
    phase_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phase_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correct_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    total_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="0.00")
    score_scale: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="50.00")
    total_answer_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    game_set: Mapped[AlbumnesiaGameSet] = relationship(back_populates="attempts")
    participant: Mapped[AlbumnesiaParticipant | None] = relationship(back_populates="attempts")
    submissions: Mapped[list[AlbumnesiaRoundSubmission]] = relationship(back_populates="attempt", cascade="all, delete-orphan", order_by="AlbumnesiaRoundSubmission.round_number")


class AlbumnesiaRoundSubmission(TimestampMixin, Base):
    __tablename__ = "albumnesia_round_submissions"
    __table_args__ = (
        CheckConstraint("round_number BETWEEN 1 AND 5", name="albumnesia_submission_round_range"),
        CheckConstraint("remaining_ms BETWEEN 0 AND 5000", name="albumnesia_remaining_ms_range"),
        CheckConstraint("answer_time_ms BETWEEN 0 AND 5000", name="albumnesia_answer_time_ms_range"),
        CheckConstraint("awarded_score BETWEEN 0 AND 50", name="albumnesia_round_score_range"),
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.albumnesia_attempts.id", ondelete="CASCADE"), primary_key=True)
    round_number: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    submitted_title: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    remaining_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    awarded_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    attempt: Mapped[AlbumnesiaAttempt] = relationship(back_populates="submissions")


class AlbumnesiaDailyProgress(UpdatedTimestampMixin, Base):
    __tablename__ = "albumnesia_daily_progress"
    __table_args__ = (
        CheckConstraint("current_streak >= 0", name="albumnesia_current_streak_nonnegative"),
        CheckConstraint("longest_streak >= 0", name="albumnesia_longest_streak_nonnegative"),
    )
    guest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_completed_date: Mapped[date | None] = mapped_column(Date)


class BadlyGameSet(TimestampMixin, Base):
    __tablename__ = "badly_game_sets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    game_date: Mapped[date | None] = mapped_column(Date)
    content_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{SCHEMA}.content_entries.id", ondelete="SET NULL"))
    title_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_answer_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    alternative_answers_snapshot: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    clues_snapshot: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    image_key_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    room: Mapped[BadlyRoom | None] = relationship(back_populates="game_set", cascade="all, delete-orphan", uselist=False)
    attempts: Mapped[list[BadlyAttempt]] = relationship(back_populates="game_set", cascade="all, delete-orphan")


class BadlyRoom(TimestampMixin, Base):
    __tablename__ = "badly_rooms"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    game_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.badly_game_sets.id", ondelete="CASCADE"), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    host_display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    game_set: Mapped[BadlyGameSet] = relationship(back_populates="room")
    participants: Mapped[list[BadlyParticipant]] = relationship(back_populates="room", cascade="all, delete-orphan")


class BadlyParticipant(TimestampMixin, Base):
    __tablename__ = "badly_participants"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.badly_rooms.id", ondelete="CASCADE"), nullable=False)
    guest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    room: Mapped[BadlyRoom] = relationship(back_populates="participants")
    attempt: Mapped[BadlyAttempt | None] = relationship(back_populates="participant", cascade="all, delete-orphan", uselist=False)


class BadlyAttempt(UpdatedTimestampMixin, Base):
    __tablename__ = "badly_attempts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    game_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.badly_game_sets.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{SCHEMA}.badly_participants.id", ondelete="CASCADE"))
    guest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="playing")
    phase: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ready")
    current_round: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    phase_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    successful_round: Mapped[int | None] = mapped_column(SmallInteger)
    successful_remaining_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    game_set: Mapped[BadlyGameSet] = relationship(back_populates="attempts")
    participant: Mapped[BadlyParticipant | None] = relationship(back_populates="attempt")
    submissions: Mapped[list[BadlySubmission]] = relationship(back_populates="attempt", cascade="all, delete-orphan", order_by="BadlySubmission.round_number")


class BadlySubmission(TimestampMixin, Base):
    __tablename__ = "badly_submissions"
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.badly_attempts.id", ondelete="CASCADE"), primary_key=True)
    round_number: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    submitted_title: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    remaining_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[BadlyAttempt] = relationship(back_populates="submissions")


class BadlyDailyProgress(UpdatedTimestampMixin, Base):
    __tablename__ = "badly_daily_progress"
    guest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_completed_date: Mapped[date | None] = mapped_column(Date)


class DailyPuzzle(UpdatedTimestampMixin, Base):
    __tablename__ = "daily_puzzles"
    __table_args__ = (
        CheckConstraint("close_at IS NULL OR publish_at IS NULL OR close_at > publish_at", name="valid_publication_window"),
        Index("daily_puzzles_lookup_idx", "category_id", "puzzle_date", "status"),
        Index(
            "one_active_daily_puzzle_per_category", "category_id", "puzzle_date", unique=True,
            postgresql_where=text("status IN ('scheduled', 'published')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    puzzle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.puzzles.id", ondelete="RESTRICT"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.categories.id", ondelete="RESTRICT"), nullable=False)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.rule_sets.id", ondelete="RESTRICT"), nullable=False)
    puzzle_date: Mapped[date] = mapped_column(Date, nullable=False)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[PublicationStatus] = mapped_column(pg_enum(PublicationStatus, "publication_status"), nullable=False, server_default="draft")
    puzzle: Mapped[Puzzle] = relationship(back_populates="daily_puzzles")
    category: Mapped[Category] = relationship()
    rule_set: Mapped[RuleSet] = relationship(back_populates="daily_puzzles")
    sessions: Mapped[list[GameSession]] = relationship(back_populates="daily_puzzle")


class User(UpdatedTimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("char_length(username) BETWEEN 3 AND 30", name="username_length"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    username: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sessions: Mapped[list[GameSession]] = relationship(back_populates="user")


class GameSession(UpdatedTimestampMixin, Base):
    __tablename__ = "game_sessions"
    __table_args__ = (
        CheckConstraint("current_round BETWEEN 1 AND 10", name="current_round_range"),
        CheckConstraint("wrong_guess_count >= 0", name="wrong_guess_count_nonnegative"),
        CheckConstraint("replay_count >= 0", name="replay_count_nonnegative"),
        CheckConstraint("active_guess_ms >= 0", name="active_guess_ms_nonnegative"),
        CheckConstraint("final_score >= 0", name="final_score_nonnegative"),
        CheckConstraint("solved_round IS NULL OR solved_round BETWEEN 1 AND 5", name="solved_round_range"),
        CheckConstraint("user_id IS NOT NULL OR guest_id IS NOT NULL", name="session_has_player"),
        CheckConstraint("(status = 'playing' AND completed_at IS NULL AND final_score IS NULL) OR (status <> 'playing' AND completed_at IS NOT NULL)", name="completed_session_shape"),
        Index("one_registered_attempt_per_daily_puzzle", "daily_puzzle_id", "user_id", unique=True, postgresql_where=text("user_id IS NOT NULL")),
        Index("one_guest_attempt_per_daily_puzzle", "daily_puzzle_id", "guest_id", unique=True, postgresql_where=text("guest_id IS NOT NULL")),
        Index("game_sessions_user_history_idx", "user_id", text("started_at DESC"), postgresql_where=text("user_id IS NOT NULL")),
        Index("game_sessions_daily_score_idx", "daily_puzzle_id", text("final_score DESC"), "completed_at", postgresql_where=text("status = 'won'")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    daily_puzzle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.daily_puzzles.id", ondelete="RESTRICT"), nullable=False)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.rule_sets.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"))
    guest_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[SessionStatus] = mapped_column(pg_enum(SessionStatus, "session_status"), nullable=False, server_default="playing")
    current_round: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    wrong_guess_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    replay_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    hint_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cryptic_hint_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    title_pattern_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cryptic_hint_unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title_pattern_unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    guess_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    solved_round: Mapped[int | None] = mapped_column(SmallInteger)
    active_guess_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    final_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    daily_puzzle: Mapped[DailyPuzzle] = relationship(back_populates="sessions")
    rule_set: Mapped[RuleSet] = relationship()
    user: Mapped[User | None] = relationship(back_populates="sessions")
    guesses: Mapped[list[Guess]] = relationship(back_populates="session", cascade="all, delete-orphan")
    events: Mapped[list[SessionEvent]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Guess(TimestampMixin, Base):
    __tablename__ = "guesses"
    __table_args__ = (
        CheckConstraint("round_number BETWEEN 1 AND 10", name="round_number_range"),
        CheckConstraint("btrim(submitted_title) <> ''", name="submitted_title_not_blank"),
        CheckConstraint("response_time_ms >= 0", name="response_time_nonnegative"),
        CheckConstraint("applied_wrong_guess_penalty >= 0", name="applied_penalty_nonnegative"),
        CheckConstraint("hints_used_count BETWEEN 0 AND 2", name="hints_used_count_range"),
        UniqueConstraint("session_id", "round_number", name="one_guess_per_round"),
        Index("guesses_session_idx", "session_id", "round_number"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.game_sessions.id", ondelete="CASCADE"), nullable=False)
    round_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    submitted_title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_submission: Mapped[str] = mapped_column(Text, Computed("normalize_title(submitted_title)", persisted=True))
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_wrong_guess_penalty: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default="0.00")
    hints_used_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    session: Mapped[GameSession] = relationship(back_populates="guesses")


class SessionEvent(Base):
    __tablename__ = "session_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('glimpse_shown', 'glimpse_replayed', 'hint_unlocked')", name="event_type_allowed"),
        CheckConstraint("round_number BETWEEN 1 AND 10", name="round_number_range"),
        Index("session_events_session_idx", "session_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.game_sessions.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    round_number: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    session: Mapped[GameSession] = relationship(back_populates="events")
