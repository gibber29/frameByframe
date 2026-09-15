import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.models.entities import ContentStatus, MediaType


class StagedUploadRead(BaseModel):
    stage_id: str
    sanitized_filename: str
    width: int
    height: int
    size_bytes: int
    image_url: str


class ClassificationRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_playable: bool


class ClassificationCatalogRead(BaseModel):
    playable_categories: list[ClassificationRead]
    tags: list[ClassificationRead]


class TagWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tag name must not be blank")
        return value


class NewMovieWrite(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    release_year: int | None = Field(default=None, ge=1888, le=2200)
    media_type: MediaType = MediaType.MOVIE

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Movie title must not be blank")
        return value


class AssetRead(BaseModel):
    asset_id: str
    movie_id: uuid.UUID
    movie_title: str
    image_key: str
    image_url: str
    suggested_hint: str | None


class RevealStageRead(BaseModel):
    round_number: int
    radius_percent: Decimal | None
    duration_ms: int | None
    show_full_image: bool


class RevealProfileRead(BaseModel):
    id: uuid.UUID
    name: str
    stages: list[RevealStageRead]


class AssetCatalogRead(BaseModel):
    assets: list[AssetRead]
    reveal_profiles: list[RevealProfileRead]


class PuzzleStageRegionWrite(BaseModel):
    round_number: int = Field(ge=1, le=4)
    reveal_x: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    reveal_y: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class PuzzleStageRegionRead(PuzzleStageRegionWrite):
    model_config = ConfigDict(from_attributes=True)


def validate_unique_rounds(regions: list[PuzzleStageRegionWrite]) -> list[PuzzleStageRegionWrite]:
    rounds = [region.round_number for region in regions]
    if len(rounds) != len(set(rounds)):
        raise ValueError("Each reveal round can have only one region")
    return regions


class PuzzleWrite(BaseModel):
    movie_id: uuid.UUID
    image_key: str
    stage_regions: list[PuzzleStageRegionWrite] = Field(default_factory=list, max_length=4)
    cryptic_hint: str
    difficulty: int = Field(ge=1, le=5)
    reveal_profile_id: uuid.UUID
    status: ContentStatus = ContentStatus.DRAFT

    @field_validator("cryptic_hint")
    @classmethod
    def hint_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Cryptic hint must not be blank")
        return value

    @field_validator("stage_regions")
    @classmethod
    def rounds_must_be_unique(cls, value: list[PuzzleStageRegionWrite]) -> list[PuzzleStageRegionWrite]:
        return validate_unique_rounds(value)


class PuzzlePatch(BaseModel):
    movie_id: uuid.UUID | None = None
    image_key: str | None = None
    stage_regions: list[PuzzleStageRegionWrite] | None = Field(default=None, max_length=4)
    cryptic_hint: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    reveal_profile_id: uuid.UUID | None = None
    status: ContentStatus | None = None
    category_ids: list[uuid.UUID] | None = None
    tag_ids: list[uuid.UUID] | None = None

    @model_validator(mode="after")
    def supplied_fields_must_not_be_null(self) -> "PuzzlePatch":
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self

    @field_validator("cryptic_hint")
    @classmethod
    def hint_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Cryptic hint must not be blank")
        return value

    @field_validator("stage_regions")
    @classmethod
    def rounds_must_be_unique(cls, value: list[PuzzleStageRegionWrite] | None) -> list[PuzzleStageRegionWrite] | None:
        return validate_unique_rounds(value) if value is not None else None


class PuzzleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    movie_id: uuid.UUID
    movie_title: str
    image_key: str
    stage_regions: list[PuzzleStageRegionRead]
    cryptic_hint: str
    difficulty: int
    reveal_profile_id: uuid.UUID
    reveal_profile_name: str
    reveal_stages: list[RevealStageRead]
    status: ContentStatus
    image_url: str
    category_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)


class CompletePuzzleWrite(BaseModel):
    staged_upload_id: str
    existing_movie_id: uuid.UUID | None = None
    new_movie: NewMovieWrite | None = None
    category_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    stage_regions: list[PuzzleStageRegionWrite] = Field(default_factory=list, max_length=4)
    cryptic_hint: str
    difficulty: int = Field(ge=1, le=5)
    reveal_profile_id: uuid.UUID
    status: ContentStatus = ContentStatus.DRAFT

    @model_validator(mode="after")
    def exactly_one_movie_source(self) -> "CompletePuzzleWrite":
        if (self.existing_movie_id is None) == (self.new_movie is None):
            raise ValueError("Select an existing movie or supply one new movie")
        validate_unique_rounds(self.stage_regions)
        self.cryptic_hint = self.cryptic_hint.strip()
        if not self.cryptic_hint:
            raise ValueError("Cryptic hint must not be blank")
        return self


class ReplaceImageWrite(BaseModel):
    staged_upload_id: str
