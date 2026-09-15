import uuid

from backend.app.models.entities import Category, Movie
from backend.app.repositories.categories import CategoryRepository
from backend.app.repositories.movies import MovieRepository


class CatalogService:
    def __init__(self, categories: CategoryRepository, movies: MovieRepository) -> None:
        self.categories = categories
        self.movies = movies

    def list_categories(self) -> list[Category]:
        return self.categories.list_active()

    def list_movies(self) -> list[Movie]:
        return self.movies.list()

    def get_movie(self, movie_id: uuid.UUID) -> Movie | None:
        return self.movies.get(movie_id)
