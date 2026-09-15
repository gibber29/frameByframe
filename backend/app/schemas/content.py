import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContentCategory = Literal["badly_explained", "albumnesia", "guess_assemble"]
DistortionTechnique = Literal[
    "pixel_hangover", "sleeve_shredder", "channel_damage", "identity_crisis",
    "outline_only",
]
ALL_DISTORTIONS = [
    "pixel_hangover", "sleeve_shredder", "channel_damage", "identity_crisis",
    "outline_only",
]


def clean_nonblank(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} must not be blank")
    return value


def clean_alternatives(values: list[str]) -> list[str]:
    cleaned = [clean_nonblank(value, "Alternative answer") for value in values]
    normalized = ["".join(character for character in value.casefold() if character.isalnum()) for value in cleaned]
    if len(normalized) != len(set(normalized)):
        raise ValueError("Alternative answers must be unique")
    return cleaned


class Point(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class MaskRegion(BaseModel):
    kind: Literal["rectangle", "polygon"]
    points: list[Point] = Field(min_length=2, max_length=30)

    @model_validator(mode="after")
    def shape_has_correct_points(self) -> "MaskRegion":
        if self.kind == "rectangle" and len(self.points) != 2:
            raise ValueError("Rectangle masks require exactly two corner points")
        if self.kind == "polygon" and len(self.points) < 3:
            raise ValueError("Polygon masks require at least three points")
        return self


class SharedContentWrite(BaseModel):
    alternative_answers: list[str] = Field(default_factory=list, max_length=30)
    difficulty: int = Field(ge=1, le=5)
    is_active: bool = False

    @field_validator("alternative_answers")
    @classmethod
    def alternatives_are_clean(cls, value: list[str]) -> list[str]:
        return clean_alternatives(value)


class BadlyExplainedWrite(SharedContentWrite):
    title: str = Field(min_length=1, max_length=300)
    clues: tuple[str, str, str, str]
    staged_upload_id: str

    @field_validator("title")
    @classmethod
    def title_is_clean(cls, value: str) -> str:
        return clean_nonblank(value, "Title")

    @field_validator("clues")
    @classmethod
    def clues_are_nonblank(cls, value: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
        return tuple(clean_nonblank(clue, f"Clue {index}") for index, clue in enumerate(value, 1))  # type: ignore[return-value]


class BadlyExplainedPatch(BaseModel):
    title: str | None = None
    clues: tuple[str, str, str, str] | None = None
    alternative_answers: list[str] | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    is_active: bool | None = None

    @field_validator("title")
    @classmethod
    def title_is_clean(cls, value: str | None) -> str | None:
        return clean_nonblank(value, "Title") if value is not None else value

    @field_validator("clues")
    @classmethod
    def clues_are_nonblank(cls, value):
        return tuple(clean_nonblank(clue, f"Clue {index}") for index, clue in enumerate(value, 1)) if value else value

    @field_validator("alternative_answers")
    @classmethod
    def alternatives_are_clean(cls, value):
        return clean_alternatives(value) if value is not None else value

    @model_validator(mode="after")
    def supplied_fields_are_not_null(self) -> "BadlyExplainedPatch":
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name.replace('_', ' ').title()} cannot be null")
        return self


class AlbumnesiaWrite(SharedContentWrite):
    model_config = ConfigDict(extra="forbid")
    album_title: str = Field(min_length=1, max_length=300)
    artist: str = Field(min_length=1, max_length=300)
    release_year: int | None = Field(default=None, ge=1888, le=2200)
    recognizable_track: str = Field(min_length=1, max_length=300)
    artist_initials: str = Field(min_length=1, max_length=30)
    enabled_distortions: list[DistortionTechnique] = Field(default_factory=lambda: list(ALL_DISTORTIONS))
    text_mask_regions: list[MaskRegion] = Field(default_factory=list, max_length=50)
    subject_mask_regions: list[MaskRegion] = Field(default_factory=list, max_length=20)
    staged_upload_id: str

    @field_validator("album_title", "artist", "recognizable_track", "artist_initials")
    @classmethod
    def required_text_is_clean(cls, value: str, info) -> str:
        return clean_nonblank(value, info.field_name.replace("_", " ").title())

    @field_validator("enabled_distortions")
    @classmethod
    def distortions_are_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Distortion techniques must be unique")
        return value

    @model_validator(mode="after")
    def active_album_is_playable(self) -> "AlbumnesiaWrite":
        if self.is_active and not self.enabled_distortions:
            raise ValueError("An active album requires at least one enabled distortion")
        if self.is_active and "identity_crisis" in self.enabled_distortions and not self.subject_mask_regions:
            raise ValueError("Identity Crisis requires at least one subject region")
        return self


class AlbumnesiaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    album_title: str | None = None
    artist: str | None = None
    alternative_answers: list[str] | None = None
    release_year: int | None = Field(default=None, ge=1888, le=2200)
    recognizable_track: str | None = None
    artist_initials: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    is_active: bool | None = None
    enabled_distortions: list[DistortionTechnique] | None = None
    text_mask_regions: list[MaskRegion] | None = Field(default=None, max_length=50)
    subject_mask_regions: list[MaskRegion] | None = Field(default=None, max_length=20)

    @field_validator("album_title", "artist", "recognizable_track", "artist_initials")
    @classmethod
    def supplied_text_is_clean(cls, value: str | None, info):
        return clean_nonblank(value, info.field_name.replace("_", " ").title()) if value is not None else value

    @field_validator("alternative_answers")
    @classmethod
    def alternatives_are_clean(cls, value):
        return clean_alternatives(value) if value is not None else value

    @field_validator("enabled_distortions")
    @classmethod
    def distortions_are_unique(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Distortion techniques must be unique")
        return value

    @model_validator(mode="after")
    def supplied_fields_are_not_null(self) -> "AlbumnesiaPatch":
        nullable_fields = {"release_year"}
        for field_name in self.model_fields_set - nullable_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name.replace('_', ' ').title()} cannot be null")
        return self


class ContentRead(BaseModel):
    id: uuid.UUID
    category: ContentCategory
    primary_answer: str
    alternative_answers: list[str]
    image_url: str
    difficulty: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    clues: list[str] | None = None
    artist: str | None = None
    release_year: int | None = None
    recognizable_track: str | None = None
    artist_initials: str | None = None
    enabled_distortions: list[str] | None = None
    text_mask_regions: list[dict] | None = None
    subject_mask_regions: list[dict] | None = None


class DuplicateContentWrite(BaseModel):
    primary_answer: str | None = None
