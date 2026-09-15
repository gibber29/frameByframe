from backend.app.db.base import Base, SCHEMA
from backend.app import models  # noqa: F401
from sqlalchemy import Numeric


def test_all_models_use_the_application_schema() -> None:
    expected_tables = {
        "categories", "movies", "movie_categories", "reveal_profiles", "reveal_stages",
        "rule_sets", "rule_set_wrong_guess_penalties", "puzzles", "puzzle_categories", "puzzle_messages", "daily_puzzles",
        "puzzle_stage_regions", "users", "game_sessions", "guesses", "session_events",
        "content_entries", "badly_explained_content", "albumnesia_content",
        "albumnesia_game_sets", "albumnesia_game_rounds", "albumnesia_rooms",
        "albumnesia_participants", "albumnesia_attempts", "albumnesia_round_submissions",
        "albumnesia_daily_progress",
        "badly_game_sets", "badly_rooms", "badly_participants", "badly_attempts",
        "badly_submissions", "badly_daily_progress",
    }

    assert set(Base.metadata.tables) == {f"{SCHEMA}.{name}" for name in expected_tables}


def test_movie_model_preserves_generated_title_and_identity_constraint() -> None:
    table = Base.metadata.tables[f"{SCHEMA}.movies"]

    assert table.c.normalized_title.computed is not None
    assert table.c.normalized_title.computed.persisted is True
    assert any(constraint.name == "movies_identity_unique" for constraint in table.constraints)


def test_partial_unique_session_indexes_are_mapped() -> None:
    table = Base.metadata.tables[f"{SCHEMA}.game_sessions"]
    indexes = {index.name: index for index in table.indexes}

    assert indexes["one_registered_attempt_per_daily_puzzle"].unique
    assert indexes["one_guest_attempt_per_daily_puzzle"].unique
    assert indexes["one_registered_attempt_per_daily_puzzle"].dialect_options["postgresql"]["where"] is not None


def test_puzzle_regions_use_a_composite_key_and_puzzles_have_no_shared_coordinates() -> None:
    puzzle = Base.metadata.tables[f"{SCHEMA}.puzzles"]
    regions = Base.metadata.tables[f"{SCHEMA}.puzzle_stage_regions"]

    assert "reveal_x" not in puzzle.c
    assert "reveal_y" not in puzzle.c
    assert {column.name for column in regions.primary_key.columns} == {"puzzle_id", "round_number"}


def test_scores_and_penalties_use_fixed_point_numeric_columns() -> None:
    rules = Base.metadata.tables[f"{SCHEMA}.rule_sets"]
    penalties = Base.metadata.tables[f"{SCHEMA}.rule_set_wrong_guess_penalties"]
    sessions = Base.metadata.tables[f"{SCHEMA}.game_sessions"]
    guesses = Base.metadata.tables[f"{SCHEMA}.guesses"]

    for column in (
        rules.c.base_score, rules.c.max_score, rules.c.cryptic_hint_penalty,
        rules.c.title_pattern_penalty, rules.c.minimum_correct_score,
        penalties.c.penalty_amount, sessions.c.final_score,
        guesses.c.applied_wrong_guess_penalty,
    ):
        assert isinstance(column.type, Numeric)
        assert column.type.precision == 8 and column.type.scale == 2
    assert "rule_set_id" in sessions.c


def test_managed_content_uses_shared_and_category_specific_tables() -> None:
    shared = Base.metadata.tables[f"{SCHEMA}.content_entries"]
    badly = Base.metadata.tables[f"{SCHEMA}.badly_explained_content"]
    album = Base.metadata.tables[f"{SCHEMA}.albumnesia_content"]

    assert shared.c.normalized_answer.computed is not None
    assert shared.c.image_key.unique
    assert badly.c.content_id.primary_key
    assert album.c.content_id.primary_key
    assert "crop_focus_x" not in album.c
    assert "crop_focus_y" not in album.c
    assert any(constraint.name.endswith("album_distortions_allowed") for constraint in album.constraints)
