from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.entities import Category, MediaType, Movie, MovieCategory, Puzzle, PuzzleCategory, RevealProfile


class PuzzleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _detail_options():
        return (
            selectinload(Puzzle.movie).selectinload(Movie.movie_categories).selectinload(MovieCategory.category),
            selectinload(Puzzle.reveal_profile).selectinload(RevealProfile.stages),
            selectinload(Puzzle.stage_regions),
            selectinload(Puzzle.puzzle_categories).selectinload(PuzzleCategory.category),
        )

    def list(self) -> list[Puzzle]:
        statement = select(Puzzle).options(*self._detail_options()).order_by(Puzzle.created_at.desc())
        return list(self.session.scalars(statement))

    def get(self, puzzle_id: uuid.UUID) -> Puzzle | None:
        return self.session.scalar(select(Puzzle).where(Puzzle.id == puzzle_id).options(*self._detail_options()))

    def get_by_image_key(self, image_key: str) -> Puzzle | None:
        return self.session.scalar(select(Puzzle).where(Puzzle.image_key == image_key))

    def get_movie(self, movie_id: uuid.UUID) -> Movie | None:
        return self.session.get(Movie, movie_id)

    def get_profile(self, profile_id: uuid.UUID) -> RevealProfile | None:
        return self.session.scalar(
            select(RevealProfile).where(RevealProfile.id == profile_id).options(selectinload(RevealProfile.stages))
        )

    def list_profiles(self) -> list[RevealProfile]:
        return list(self.session.scalars(select(RevealProfile).options(selectinload(RevealProfile.stages)).order_by(RevealProfile.name)))

    def list_movies(self) -> list[Movie]:
        return list(self.session.scalars(select(Movie).order_by(Movie.title)))

    def list_categories(self) -> list[Category]:
        return list(self.session.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.name)))

    def get_categories(self, category_ids: set[uuid.UUID]) -> list[Category]:
        if not category_ids:
            return []
        return list(self.session.scalars(select(Category).where(Category.id.in_(category_ids), Category.is_active.is_(True))))

    def duplicate_movie(self, title: str, release_year: int | None, media_type: MediaType) -> Movie | None:
        return self.session.scalar(select(Movie).where(
            Movie.normalized_title == func.normalize_title(title),
            Movie.release_year.is_not_distinct_from(release_year),
            Movie.type == media_type,
        ))

    def get_category_by_name(self, name: str) -> Category | None:
        return self.session.scalar(select(Category).where(Category.name == name))

    def add(self, puzzle: Puzzle) -> Puzzle:
        self.session.add(puzzle)
        self.session.commit()
        return self.get(puzzle.id)  # type: ignore[return-value]

    def save(self, puzzle: Puzzle) -> Puzzle:
        self.session.commit()
        return self.get(puzzle.id)  # type: ignore[return-value]
