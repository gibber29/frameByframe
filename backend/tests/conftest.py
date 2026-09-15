import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://framebyframe:framebyframe_dev_password@db:5432/framebyframe",
)

import pytest
from sqlalchemy import delete, select

from backend.app.db.seed import seed_database
from backend.app.db.session import SessionLocal
from backend.app.models.entities import (
    Category, ContentEntry, DailyPuzzle, GameSession, Movie, Puzzle, RuleSet, User,
)


@pytest.fixture(scope="session", autouse=True)
def seeded_database() -> None:
    seed_database()
    tracked_models = (GameSession, DailyPuzzle, ContentEntry, Puzzle, User, Movie, Category, RuleSet)
    with SessionLocal() as session:
        original_ids = {
            model: set(session.scalars(select(model.id)))
            for model in tracked_models
        }
    yield
    # Tests run against the Docker development database, so remove only rows
    # introduced by the suite and leave every pre-existing identifier intact.
    with SessionLocal.begin() as session:
        for model in tracked_models:
            session.execute(delete(model).where(model.id.not_in(original_ids[model])))
