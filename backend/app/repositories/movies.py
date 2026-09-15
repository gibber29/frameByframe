import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.entities import Movie, MovieCategory


class MovieRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _with_categories():
        return selectinload(Movie.movie_categories).selectinload(MovieCategory.category)

    def list(self) -> list[Movie]:
        statement = select(Movie).options(self._with_categories()).order_by(Movie.title)
        return list(self.session.scalars(statement))

    def get(self, movie_id: uuid.UUID) -> Movie | None:
        statement = select(Movie).where(Movie.id == movie_id).options(self._with_categories())
        return self.session.scalar(statement)
