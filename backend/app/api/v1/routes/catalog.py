import uuid

from fastapi import APIRouter, HTTPException, status

from backend.app.api.dependencies import CatalogServiceDependency
from backend.app.schemas.catalog import CategoryRead, MovieRead

router = APIRouter(tags=["catalog"])


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(service: CatalogServiceDependency) -> list[CategoryRead]:
    return [CategoryRead.model_validate(category) for category in service.list_categories()]


@router.get("/movies", response_model=list[MovieRead])
def list_movies(service: CatalogServiceDependency) -> list[MovieRead]:
    return [MovieRead.from_model(movie) for movie in service.list_movies()]


@router.get("/movies/{movie_id}", response_model=MovieRead)
def get_movie(movie_id: uuid.UUID, service: CatalogServiceDependency) -> MovieRead:
    movie = service.get_movie(movie_id)
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return MovieRead.from_model(movie)
