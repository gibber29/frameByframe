"""Idempotent reference-data seed. Run after ``alembic upgrade head``."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.app.db.session import SessionLocal
from backend.app.models.entities import (
    Category,
    CategoryType,
    MediaType,
    Movie,
    MovieCategory,
    RevealProfile,
    RevealStage,
    RuleSet,
    RuleSetWrongGuessPenalty,
)

CATEGORIES = (
    {"name": "Anime", "slug": "anime", "type": CategoryType.GENRE, "is_playable": True},
    {"name": "Superheroes", "slug": "superheroes", "type": CategoryType.GENRE, "is_playable": True},
    {"name": "Disney & Pixar", "slug": "disney-pixar", "type": CategoryType.COLLECTION, "is_playable": True},
    {"name": "All-Time Greats", "slug": "all-time-greats", "type": CategoryType.COLLECTION, "is_playable": True},
    {"name": "Marvel", "slug": "marvel", "type": CategoryType.UNIVERSE, "is_playable": False},
    {"name": "DC", "slug": "dc", "type": CategoryType.UNIVERSE, "is_playable": False},
    {"name": "Pixar", "slug": "pixar", "type": CategoryType.COLLECTION, "is_playable": False},
    {"name": "Disney", "slug": "disney", "type": CategoryType.COLLECTION, "is_playable": False},
    {"name": "Studio Ghibli", "slug": "studio-ghibli", "type": CategoryType.COLLECTION, "is_playable": False},
)

MOVIES = (
    ("Ant-Man", 2015, MediaType.MOVIE),
    ("Avengers: Endgame", 2019, MediaType.MOVIE),
    ("Avengers: Infinity War", 2018, MediaType.MOVIE),
    ("Black Panther", 2018, MediaType.MOVIE),
    ("Captain America: The Winter Soldier", 2014, MediaType.MOVIE),
    ("Captain America: Civil War", 2016, MediaType.MOVIE),
    ("Deadpool & Wolverine", 2024, MediaType.MOVIE),
    ("Doctor Strange", 2016, MediaType.MOVIE),
    ("Guardians of the Galaxy", 2014, MediaType.MOVIE),
    ("Guardians of the Galaxy Vol. 2", 2017, MediaType.MOVIE),
    ("Iron Man", 2008, MediaType.MOVIE),
    ("Loki", 2021, MediaType.SERIES),
    ("Moon Knight", 2022, MediaType.SERIES),
    ("Spider-Man: Brand New Day", 2026, MediaType.MOVIE),
    ("Spider-Man: Homecoming", 2017, MediaType.MOVIE),
    ("Spider-Man: No Way Home", 2021, MediaType.MOVIE),
)


def seed_database() -> None:
    with SessionLocal.begin() as session:
        for values in CATEGORIES:
            statement = insert(Category).values(**values).on_conflict_do_update(
                index_elements=[Category.slug],
                set_={
                    "name": values["name"], "type": values["type"],
                    "is_playable": values["is_playable"], "is_active": True,
                },
            )
            session.execute(statement)

        profile_statement = insert(RevealProfile).values(
            name="Default five-turn reveal",
            description="Four expanding timed circles followed by the complete frame.",
        ).on_conflict_do_update(
            index_elements=[RevealProfile.name],
            set_={"description": "Four expanding timed circles followed by the complete frame."},
        ).returning(RevealProfile.id)
        profile_id = session.execute(profile_statement).scalar_one()

        stages = (
            (1, Decimal("14.00"), 200, False),
            (2, Decimal("22.00"), 300, False),
            (3, Decimal("32.00"), 300, False),
            (4, Decimal("45.00"), 400, False),
            (5, None, 500, True),
        )
        for round_number, radius, duration, full_image in stages:
            session.execute(
                insert(RevealStage).values(
                    profile_id=profile_id, round_number=round_number,
                    radius_percent=radius, duration_ms=duration, show_full_image=full_image,
                ).on_conflict_do_update(
                    index_elements=[RevealStage.profile_id, RevealStage.round_number],
                    set_={"radius_percent": radius, "duration_ms": duration, "show_full_image": full_image},
                )
            )

        rules = {
            "name": "Daily gameplay v1", "base_score": Decimal("1000.00"),
            "max_score": Decimal("1000.00"),
            "time_penalty_per_second": Decimal("5.00"), "replay_penalty": 0,
            "cryptic_hint_penalty": 50, "title_pattern_penalty": 100,
            "minimum_correct_score": 100, "max_attempts": 5, "score_decimal_places": 0,
        }
        rule_set_id = session.execute(
            insert(RuleSet).values(**rules).on_conflict_do_nothing(
                index_elements=[RuleSet.name]
            ).returning(RuleSet.id)
        ).scalar_one_or_none()
        if rule_set_id is None:
            rule_set_id = session.scalar(select(RuleSet.id).where(RuleSet.name == rules["name"]))

        for round_number in range(1, 6):
            for hints_used_count in range(3):
                penalty = 100 if round_number <= 2 else (125, 150, 175)[hints_used_count]
                session.execute(
                    insert(RuleSetWrongGuessPenalty).values(
                        rule_set_id=rule_set_id,
                        round_number=round_number,
                        hints_used_count=hints_used_count,
                        penalty_amount=penalty,
                    ).on_conflict_do_nothing()
                )

        v2_rules = {
            "name": "Daily gameplay v2", "base_score": Decimal("50.00"),
            "max_score": Decimal("50.00"),
            "time_penalty_per_second": Decimal("0.05"), "replay_penalty": Decimal("0.00"),
            "cryptic_hint_penalty": Decimal("2.50"), "title_pattern_penalty": Decimal("5.00"),
            "minimum_correct_score": Decimal("0.00"), "max_attempts": 5, "score_decimal_places": 2,
        }
        v2_rule_set_id = session.execute(
            insert(RuleSet).values(**v2_rules).on_conflict_do_nothing(
                index_elements=[RuleSet.name]
            ).returning(RuleSet.id)
        ).scalar_one_or_none()
        if v2_rule_set_id is None:
            v2_rule_set_id = session.scalar(select(RuleSet.id).where(RuleSet.name == v2_rules["name"]))

        for round_number in range(1, 6):
            for hints_used_count in range(3):
                penalty = Decimal("3.00") if round_number <= 2 else (
                    Decimal("4.00"), Decimal("5.00"), Decimal("6.00")
                )[hints_used_count]
                session.execute(
                    insert(RuleSetWrongGuessPenalty).values(
                        rule_set_id=v2_rule_set_id,
                        round_number=round_number,
                        hints_used_count=hints_used_count,
                        penalty_amount=penalty,
                    ).on_conflict_do_nothing()
                )

        for title, release_year, media_type in MOVIES:
            session.execute(
                insert(Movie).values(title=title, release_year=release_year, type=media_type).on_conflict_do_nothing(
                    constraint="movies_identity_unique"
                )
            )

        category_ids = dict(
            session.execute(
                select(Category.slug, Category.id).where(Category.slug.in_(("superheroes", "marvel")))
            ).all()
        )
        movie_ids = session.scalars(select(Movie.id).where(Movie.title.in_([movie[0] for movie in MOVIES]))).all()
        for movie_id in movie_ids:
            for category_id in category_ids.values():
                session.execute(
                    insert(MovieCategory).values(movie_id=movie_id, category_id=category_id).on_conflict_do_nothing()
                )


if __name__ == "__main__":
    seed_database()
