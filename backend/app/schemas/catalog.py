import uuid

from pydantic import BaseModel, ConfigDict

from backend.app.models.entities import CategoryType, ContentStatus, MediaType


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    type: CategoryType
    is_playable: bool
    is_active: bool


class MovieRead(BaseModel):
    id: uuid.UUID
    title: str
    normalized_title: str
    release_year: int | None
    type: MediaType
    status: ContentStatus
    categories: list[CategoryRead]

    @classmethod
    def from_model(cls, movie) -> "MovieRead":
        return cls(
            id=movie.id, title=movie.title, normalized_title=movie.normalized_title,
            release_year=movie.release_year, type=movie.type, status=movie.status,
            categories=[CategoryRead.model_validate(link.category) for link in movie.movie_categories],
        )
