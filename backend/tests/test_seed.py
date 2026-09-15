from decimal import Decimal

from sqlalchemy import func, select

from backend.app.db.seed import seed_database
from backend.app.db.session import SessionLocal
from backend.app.models.entities import Category, Movie, MovieCategory, Puzzle, RevealProfile, RevealStage, RuleSet, RuleSetWrongGuessPenalty


def _counts() -> tuple[int, ...]:
    with SessionLocal() as session:
        return (
            session.scalar(select(func.count()).select_from(Category)),
            session.scalar(select(func.count()).select_from(Movie)),
            session.scalar(select(func.count()).select_from(MovieCategory)),
            session.scalar(select(func.count()).select_from(RevealProfile)),
            session.scalar(select(func.count()).select_from(RevealStage)),
            session.scalar(select(func.count()).select_from(RuleSet)),
        )


def test_seed_is_idempotent_and_contains_reference_catalog_only() -> None:
    with SessionLocal() as session:
        puzzles_before = session.scalar(select(func.count()).select_from(Puzzle))
    seed_database()
    first = _counts()
    seed_database()
    second = _counts()

    assert first == second
    assert first == (9, 16, 32, 1, 5, 3)
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Puzzle)) == puzzles_before


def test_seed_category_playability() -> None:
    with SessionLocal() as session:
        categories = {category.slug: category.is_playable for category in session.scalars(select(Category))}

    assert {slug for slug, playable in categories.items() if playable} == {
        "anime", "superheroes", "disney-pixar", "all-time-greats"
    }
    assert categories["marvel"] is False
    assert categories["dc"] is False
    assert categories["pixar"] is False
    assert categories["disney"] is False
    assert categories["studio-ghibli"] is False


def test_single_glimpse_profile_and_active_scoring_rules() -> None:
    with SessionLocal() as session:
        profile = session.scalar(
            select(RevealProfile).where(RevealProfile.name == "Default five-turn reveal")
        )
        stages = session.execute(
            select(
                RevealStage.round_number,
                RevealStage.radius_percent,
                RevealStage.duration_ms,
                RevealStage.show_full_image,
            )
            .where(RevealStage.profile_id == profile.id)
            .order_by(RevealStage.round_number)
        ).all()
        rules = session.scalar(select(RuleSet).where(RuleSet.name == "Daily gameplay v1"))

    assert stages == [
        (1, Decimal("14.00"), 200, False),
        (2, Decimal("22.00"), 300, False),
        (3, Decimal("32.00"), 300, False),
        (4, Decimal("45.00"), 400, False),
        (5, None, 500, True),
    ]
    assert (
        rules.base_score,
        rules.time_penalty_per_second,
        rules.replay_penalty,
        rules.cryptic_hint_penalty,
        rules.title_pattern_penalty,
        rules.minimum_correct_score,
    ) == (
        Decimal("1000.00"), Decimal("5.00"), Decimal("0.00"),
        Decimal("50.00"), Decimal("100.00"), Decimal("100.00"),
    )


def test_daily_gameplay_v2_decimal_rules() -> None:
    with SessionLocal() as session:
        rules = session.scalar(select(RuleSet).where(RuleSet.name == "Daily gameplay v2"))
        penalties = session.execute(
            select(
                RuleSetWrongGuessPenalty.round_number,
                RuleSetWrongGuessPenalty.hints_used_count,
                RuleSetWrongGuessPenalty.penalty_amount,
            ).where(RuleSetWrongGuessPenalty.rule_set_id == rules.id)
            .order_by(RuleSetWrongGuessPenalty.round_number, RuleSetWrongGuessPenalty.hints_used_count)
        ).all()

    assert (
        rules.base_score, rules.max_score, rules.time_penalty_per_second,
        rules.cryptic_hint_penalty, rules.title_pattern_penalty,
        rules.minimum_correct_score, rules.score_decimal_places,
    ) == (
        Decimal("50.00"), Decimal("50.00"), Decimal("0.05"),
        Decimal("2.50"), Decimal("5.00"), Decimal("0.00"), 2,
    )
    assert [row.penalty_amount for row in penalties[:6]] == [Decimal("3.00")] * 6
    assert [row.penalty_amount for row in penalties[6:9]] == [Decimal("4.00"), Decimal("5.00"), Decimal("6.00")]
