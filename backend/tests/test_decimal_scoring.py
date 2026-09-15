import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update

from backend.app.db.session import SessionLocal
from backend.app.main import create_app
from backend.app.models.entities import (
    Category, ContentStatus, DailyPuzzle, GameSession, Movie, PublicationStatus,
    Puzzle, PuzzleStageRegion, RevealProfile, RuleSet, SessionStatus, User,
)
from backend.app.repositories.game import GameRepository
from backend.app.services.gameplay import GameplayService

ANSWER = "Ant-Man"
CATEGORY = "disney-pixar"


@pytest.fixture(scope="module", autouse=True)
def v2_daily_puzzle() -> None:
    with SessionLocal.begin() as session:
        category = session.scalar(select(Category).where(Category.slug == CATEGORY))
        puzzle = session.scalar(select(Puzzle).where(Puzzle.image_key == "ant-man/ant-man.webp"))
        if puzzle is None:
            movie = session.scalar(select(Movie).where(Movie.title == ANSWER))
            profile = session.scalar(select(RevealProfile).where(
                RevealProfile.name == "Default five-turn reveal"
            ))
            puzzle = Puzzle(
                movie_id=movie.id,
                image_key="ant-man/ant-man.webp",
                cryptic_hint="The Thomas incident was greatly exaggerated.",
                difficulty=3,
                reveal_profile_id=profile.id,
                status=ContentStatus.READY,
                stage_regions=[
                    PuzzleStageRegion(round_number=n, reveal_x=20 + n, reveal_y=30 + n)
                    for n in range(1, 5)
                ],
            )
            session.add(puzzle)
            session.flush()
        rules = session.scalar(select(RuleSet).where(RuleSet.name == "Daily gameplay v2"))
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        daily = session.scalar(select(DailyPuzzle).where(
            DailyPuzzle.category_id == category.id,
            DailyPuzzle.puzzle_date == today,
            DailyPuzzle.status == PublicationStatus.PUBLISHED,
        ))
        if daily is None:
            session.add(DailyPuzzle(
                puzzle_id=puzzle.id, category_id=category.id, rule_set_id=rules.id,
                puzzle_date=today, status=PublicationStatus.PUBLISHED,
            ))


def start() -> tuple[TestClient, str]:
    client = TestClient(create_app())
    response = client.post("/api/v1/game/start", json={"category": CATEGORY})
    assert response.status_code == 200, response.text
    return client, response.json()["session_id"]


def open_guess(client: TestClient, session_id: str, active_ms: int = 0) -> None:
    response = client.post(f"/api/v1/game/{session_id}/glimpse")
    assert response.status_code == 200, response.text
    with SessionLocal.begin() as session:
        session.execute(update(GameSession).where(GameSession.id == uuid.UUID(session_id)).values(
            active_guess_ms=active_ms,
            guess_started_at=func.clock_timestamp(),
        ))


def submit_wrong(client: TestClient, session_id: str) -> dict:
    open_guess(client, session_id)
    response = client.post(f"/api/v1/game/{session_id}/guess", json={"title": "Wrong Movie"})
    assert response.status_code == 200, response.text
    return response.json()


def test_v2_wrong_penalties_hint_costs_and_failed_game_zero() -> None:
    client, session_id = start()
    assert submit_wrong(client, session_id)["raw_applied_wrong_guess_penalty"] == "3.00"
    assert submit_wrong(client, session_id)["raw_applied_wrong_guess_penalty"] == "3.00"
    assert submit_wrong(client, session_id)["raw_applied_wrong_guess_penalty"] == "4.00"

    cryptic = client.post(f"/api/v1/game/{session_id}/hints/cryptic").json()
    assert cryptic["penalty"] == "2.50"
    assert submit_wrong(client, session_id)["raw_applied_wrong_guess_penalty"] == "5.00"

    title = client.post(f"/api/v1/game/{session_id}/hints/title-pattern").json()
    assert title["penalty"] == "5.00"
    final = submit_wrong(client, session_id)["result"]
    assert final["status"] == "lost"
    assert final["final_score"] == "0.00"
    assert final["raw_final_score"] == "0.00"


def test_v2_decimal_time_precision_and_maximum_score() -> None:
    client, session_id = start()
    with SessionLocal() as session:
        game = session.get(GameSession, uuid.UUID(session_id))
        game.active_guess_ms = 1100
        service = GameplayService(GameRepository(session), "Asia/Kolkata")
        assert service.calculate_score(game) == Decimal("49.95")
        game.active_guess_ms = 0
        assert service.calculate_score(game) == Decimal("50.00")


def test_successful_v2_game_can_finish_with_zero_score() -> None:
    client, session_id = start()
    open_guess(client, session_id, active_ms=1_000_000)
    response = client.post(f"/api/v1/game/{session_id}/guess", json={"title": ANSWER})
    result = response.json()["result"]
    assert result["status"] == "won"
    assert result["final_score"] == "0.00"
    assert result["raw_final_score"] == "0.00"


def test_sessions_pin_the_rule_set_used_at_start() -> None:
    _, session_id = start()
    with SessionLocal() as session:
        game = session.get(GameSession, uuid.UUID(session_id))
        assert game.rule_set.name == "Daily gameplay v2"
        assert game.rule_set_id == game.daily_puzzle.rule_set_id


def test_historical_scores_remain_raw_but_leaderboard_normalizes_to_fifty() -> None:
    old_name = f"old-{uuid.uuid4().hex[:12]}"
    new_name = f"new-{uuid.uuid4().hex[:12]}"
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    with SessionLocal.begin() as session:
        daily = session.scalar(select(DailyPuzzle).join(Category).where(Category.slug == "superheroes"))
        v1 = session.scalar(select(RuleSet).where(RuleSet.name == "Daily gameplay v1"))
        v2 = session.scalar(select(RuleSet).where(RuleSet.name == "Daily gameplay v2"))
        old_user = User(username=old_name)
        new_user = User(username=new_name)
        session.add_all((old_user, new_user))
        session.flush()
        old_game = GameSession(
            daily_puzzle_id=daily.id, rule_set_id=v1.id, user_id=old_user.id,
            status=SessionStatus.WON, current_round=3, solved_round=3,
            final_score=Decimal("356.00"), completed_at=now,
        )
        new_game = GameSession(
            daily_puzzle_id=daily.id, rule_set_id=v2.id, user_id=new_user.id,
            status=SessionStatus.WON, current_round=3, solved_round=3,
            final_score=Decimal("17.90"), completed_at=now,
        )
        session.add_all((old_game, new_game))
        session.flush()
        old_game_id = old_game.id

    with SessionLocal() as session:
        rows = session.execute(text("""
            SELECT username, final_score, normalized_score, score_scale
            FROM framebyframe.daily_leaderboard
            WHERE username IN (:old_name, :new_name)
            ORDER BY normalized_score DESC
        """), {"old_name": old_name, "new_name": new_name}).all()
        stored_raw = session.scalar(select(GameSession.final_score).where(GameSession.id == old_game_id))

    assert stored_raw == Decimal("356.00")
    assert rows[0].username == new_name and rows[0].normalized_score == Decimal("17.90")
    assert rows[1].username == old_name and rows[1].normalized_score == Decimal("17.80")
    assert all(row.score_scale == Decimal("50.00") for row in rows)
