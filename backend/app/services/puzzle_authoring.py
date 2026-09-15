import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.models.entities import (
    Category, CategoryType, ContentStatus, Movie, MovieCategory, Puzzle,
    PuzzleCategory, PuzzleStageRegion,
)
from backend.app.repositories.puzzles import PuzzleRepository
from backend.app.schemas.admin import CompletePuzzleWrite, PuzzlePatch, PuzzleWrite
from backend.app.storage.assets import LocalAssetStorage

SELECTED_HINTS = {
    "Ant-Man": "The Thomas incident was greatly exaggerated.",
    "Avengers: Endgame": "America’s backside receives official recognition.",
    "Avengers: Infinity War": "One rabbit gets a replacement arm.",
    "Black Panther": "Sneakers become unnecessarily literal.",
    "Captain America: The Winter Soldier": "“On your left” becomes increasingly personal.",
    "Captain America: Civil War": "A plate of plums causes international problems.",
    "Deadpool & Wolverine": "A toupee survives surprisingly long.",
    "Doctor Strange": "A library book comes with unusually strict late fees.",
    "Guardians of the Galaxy": "A prosthetic leg was never actually required.",
    "Guardians of the Galaxy Vol. 2": "The trash panda accusation remains disputed.",
    "Iron Man": "One cheeseburger before the press conference.",
    "Loki": "The fish question confuses the new employee.",
    "Moon Knight": "A goldfish mysteriously grows a second fin.",
    "Spider-Man: Brand New Day": "Privacy finally arrives with terrible timing.",
    "Spider-Man: Homecoming": "The most stressful car ride in Queens.",
    "Spider-Man: No Way Home": "Rent is no longer the biggest apartment problem.",
}


class AuthoringValidationError(ValueError):
    pass


class AuthoringConflictError(ValueError):
    pass


class AuthoringNotFoundError(LookupError):
    pass


def movie_directory(movie: Movie) -> str:
    return slugify(movie.title)


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "untitled"


class PuzzleAuthoringService:
    def __init__(self, repository: PuzzleRepository, storage: LocalAssetStorage) -> None:
        self.repository = repository
        self.storage = storage

    def validate(self, values: dict, current_id: uuid.UUID | None = None) -> tuple[Movie, object]:
        movie = self.repository.get_movie(values["movie_id"])
        if movie is None:
            raise AuthoringValidationError("Selected movie does not exist")
        try:
            self.storage.resolve(values["image_key"], movie_directory(movie))
        except (ValueError, FileNotFoundError) as exc:
            raise AuthoringValidationError(str(exc)) from exc
        profile = self.repository.get_profile(values["reveal_profile_id"])
        if profile is None:
            raise AuthoringValidationError("Reveal profile does not exist")
        if values["status"] == ContentStatus.READY:
            if not profile.stages:
                raise AuthoringValidationError("Ready puzzles require a configured reveal profile")
            if not values["cryptic_hint"].strip():
                raise AuthoringValidationError("Ready puzzles require a cryptic hint")
            rounds = {
                region["round_number"] if isinstance(region, dict) else region.round_number
                for region in values["stage_regions"]
            }
            if rounds != {1, 2, 3, 4}:
                raise AuthoringValidationError("Ready puzzles require reveal regions for rounds 1 through 4")
        existing = self.repository.get_by_image_key(values["image_key"])
        if existing is not None and existing.id != current_id:
            raise AuthoringConflictError("This image already has a puzzle")
        return movie, profile

    def create(self, payload: PuzzleWrite) -> Puzzle:
        values = payload.model_dump()
        regions = values.pop("stage_regions")
        values["stage_regions"] = [PuzzleStageRegion(**region) for region in regions]
        self.validate(values)
        return self.repository.add(Puzzle(**values))

    def update(self, puzzle_id: uuid.UUID, payload: PuzzlePatch) -> Puzzle:
        puzzle = self.repository.get(puzzle_id)
        if puzzle is None:
            raise AuthoringNotFoundError("Puzzle not found")
        changes = payload.model_dump(exclude_unset=True)
        category_ids = changes.pop("category_ids", None)
        tag_ids = changes.pop("tag_ids", None)
        values = {
            "movie_id": puzzle.movie_id, "image_key": puzzle.image_key,
            "stage_regions": list(puzzle.stage_regions),
            "cryptic_hint": puzzle.cryptic_hint, "difficulty": puzzle.difficulty,
            "reveal_profile_id": puzzle.reveal_profile_id, "status": puzzle.status,
        }
        values.update(changes)
        self.validate(values, puzzle.id)
        regions = changes.pop("stage_regions", None)
        for name, value in changes.items():
            setattr(puzzle, name, value)
        if regions is not None:
            existing_by_round = {region.round_number: region for region in puzzle.stage_regions}
            requested_rounds = {region["round_number"] for region in regions}
            puzzle.stage_regions[:] = [
                region for region in puzzle.stage_regions if region.round_number in requested_rounds
            ]
            for values_for_round in regions:
                region = existing_by_round.get(values_for_round["round_number"])
                if region is None:
                    puzzle.stage_regions.append(PuzzleStageRegion(**values_for_round))
                else:
                    region.reveal_x = values_for_round["reveal_x"]
                    region.reveal_y = values_for_round["reveal_y"]
        if category_ids is not None or tag_ids is not None:
            desired_categories = set(category_ids) if category_ids is not None else {
                item.category_id for item in puzzle.puzzle_categories
            }
            desired_tags = set(tag_ids) if tag_ids is not None else {
                item.category_id for item in puzzle.movie.movie_categories if not item.category.is_playable
            }
            selected = self._classifications(desired_categories, desired_tags)
            if category_ids is not None:
                puzzle.puzzle_categories[:] = [
                    PuzzleCategory(category_id=item.id) for item in selected if item.is_playable
                ]
            if tag_ids is not None:
                puzzle.movie.movie_categories[:] = [
                    item for item in puzzle.movie.movie_categories if item.category.is_playable
                ] + [MovieCategory(category_id=item.id) for item in selected if not item.is_playable]
        return self.repository.save(puzzle)

    def _classifications(
        self, category_ids: set[uuid.UUID], tag_ids: set[uuid.UUID]
    ) -> list[Category]:
        if category_ids & tag_ids:
            raise AuthoringValidationError("A classification cannot be both a playable category and a tag")
        requested = category_ids | tag_ids
        found = self.repository.get_categories(requested)
        if len(found) != len(requested):
            raise AuthoringValidationError("One or more classifications do not exist")
        by_id = {item.id: item for item in found}
        if any(not by_id[item_id].is_playable for item_id in category_ids):
            raise AuthoringValidationError("Playable category selection contains a tag")
        if any(by_id[item_id].is_playable for item_id in tag_ids):
            raise AuthoringValidationError("Tag selection contains a playable category")
        return found

    def classifications(self) -> tuple[list[Category], list[Category]]:
        values = self.repository.list_categories()
        return [item for item in values if item.is_playable], [item for item in values if not item.is_playable]

    def create_tag(self, name: str) -> Category:
        existing = self.repository.get_category_by_name(name)
        if existing is not None:
            if existing.is_playable:
                raise AuthoringConflictError("A playable category already uses that name")
            return existing
        tag = Category(name=name, slug=slugify(name), type=CategoryType.COLLECTION, is_playable=False)
        self.repository.session.add(tag)
        try:
            self.repository.session.commit()
        except IntegrityError as exc:
            self.repository.session.rollback()
            raise AuthoringConflictError("A category or tag with that name or slug already exists") from exc
        return tag

    def create_complete(self, payload: CompletePuzzleWrite) -> Puzzle:
        session = self.repository.session
        permanent_key: str | None = None
        try:
            self.storage.staged_path(payload.staged_upload_id)
            profile = self.repository.get_profile(payload.reveal_profile_id)
            if profile is None:
                raise AuthoringValidationError("Reveal profile does not exist")
            if payload.status == ContentStatus.READY and {
                region.round_number for region in payload.stage_regions
            } != {1, 2, 3, 4}:
                raise AuthoringValidationError("Ready puzzles require reveal regions for rounds 1 through 4")
            classifications = self._classifications(set(payload.category_ids), set(payload.tag_ids))

            if payload.existing_movie_id is not None:
                movie = self.repository.get_movie(payload.existing_movie_id)
                if movie is None:
                    raise AuthoringValidationError("Selected movie does not exist")
            else:
                values = payload.new_movie
                assert values is not None
                duplicate = self.repository.duplicate_movie(values.title, values.release_year, values.media_type)
                if duplicate is not None:
                    raise AuthoringConflictError("That movie or series already exists; select it instead")
                movie = Movie(title=values.title, release_year=values.release_year, type=values.media_type)
                session.add(movie)
                session.flush()

            existing_movie_categories = set(session.scalars(
                select(MovieCategory.category_id).where(MovieCategory.movie_id == movie.id)
            ))
            for classification in classifications:
                if classification.id not in existing_movie_categories:
                    session.add(MovieCategory(movie_id=movie.id, category_id=classification.id))

            permanent_key = self.storage.finalize(payload.staged_upload_id, movie_directory(movie))
            puzzle = Puzzle(
                movie_id=movie.id,
                image_key=permanent_key,
                cryptic_hint=payload.cryptic_hint,
                difficulty=payload.difficulty,
                reveal_profile_id=payload.reveal_profile_id,
                status=payload.status,
                stage_regions=[PuzzleStageRegion(**region.model_dump()) for region in payload.stage_regions],
                puzzle_categories=[
                    PuzzleCategory(category_id=item.id) for item in classifications if item.is_playable
                ],
            )
            session.add(puzzle)
            session.commit()
            puzzle_id = puzzle.id
        except (AuthoringValidationError, AuthoringConflictError):
            session.rollback()
            if permanent_key:
                self.storage.delete(permanent_key)
            self.storage.delete_staged(payload.staged_upload_id)
            raise
        except Exception as exc:
            session.rollback()
            if permanent_key:
                self.storage.delete(permanent_key)
            self.storage.delete_staged(payload.staged_upload_id)
            if isinstance(exc, (ValueError, FileNotFoundError, OSError)):
                raise AuthoringValidationError(str(exc)) from exc
            if isinstance(exc, IntegrityError):
                raise AuthoringConflictError("Puzzle creation conflicted with existing data") from exc
            raise
        return self.repository.get(puzzle_id)  # type: ignore[return-value]

    def replace_image(self, puzzle_id: uuid.UUID, staged_upload_id: str) -> Puzzle:
        session = self.repository.session
        puzzle = self.repository.get(puzzle_id)
        if puzzle is None:
            self.storage.delete_staged(staged_upload_id)
            raise AuthoringNotFoundError("Puzzle not found")
        old_key = puzzle.image_key
        new_key: str | None = None
        try:
            new_key = self.storage.finalize(staged_upload_id, movie_directory(puzzle.movie))
            puzzle.image_key = new_key
            session.commit()
        except Exception as exc:
            session.rollback()
            if new_key:
                self.storage.delete(new_key)
            self.storage.delete_staged(staged_upload_id)
            raise AuthoringValidationError("Could not replace the puzzle image") from exc
        self.storage.delete(old_key)
        return self.repository.get(puzzle.id)  # type: ignore[return-value]
