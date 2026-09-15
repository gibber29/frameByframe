import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update

from backend.app.db.session import SessionLocal
from backend.app.main import create_app
from backend.app.models.entities import (
    Category, ContentStatus, DailyPuzzle, GameSession, Guess, Movie, PublicationStatus,
    Puzzle, PuzzleStageRegion, RevealProfile, RuleSet, SessionStatus, User,
)
from backend.app.repositories.game import GameRepository
from backend.app.services.gameplay import GameplayService

ANSWER = "Ant-Man"


@pytest.fixture(scope="module", autouse=True)
def published_game() -> None:
    with SessionLocal.begin() as session:
        movie = session.scalar(select(Movie).where(Movie.title == ANSWER))
        profile = session.scalar(select(RevealProfile).where(RevealProfile.name == "Default five-turn reveal"))
        category = session.scalar(select(Category).where(Category.slug == "superheroes"))
        rules = session.scalar(select(RuleSet).where(RuleSet.name == "Daily gameplay v1"))
        puzzle = session.scalar(select(Puzzle).where(Puzzle.image_key == "ant-man/ant-man.webp"))
        if puzzle is None:
            puzzle = Puzzle(
                movie_id=movie.id, image_key="ant-man/ant-man.webp", cryptic_hint="The Thomas incident was greatly exaggerated.",
                difficulty=3, reveal_profile_id=profile.id, status=ContentStatus.READY,
                stage_regions=[PuzzleStageRegion(round_number=n, reveal_x=20 + n, reveal_y=30 + n) for n in range(1, 5)],
            )
            session.add(puzzle)
            session.flush()
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        daily = session.scalar(select(DailyPuzzle).where(DailyPuzzle.category_id == category.id, DailyPuzzle.puzzle_date == today, DailyPuzzle.status == PublicationStatus.PUBLISHED))
        if daily is None:
            session.add(DailyPuzzle(
                puzzle_id=puzzle.id, category_id=category.id, rule_set_id=rules.id,
                puzzle_date=today, status=PublicationStatus.PUBLISHED,
            ))


def client() -> TestClient:
    return TestClient(create_app())


def start(game_client: TestClient, category: str = "superheroes") -> dict:
    response = game_client.post("/api/v1/game/start", json={"category": category})
    assert response.status_code == 200, response.text
    return response.json()


def open_guess(session_id: str, seconds_ago: float = 0) -> None:
    with SessionLocal.begin() as session:
        session.execute(
            update(GameSession).where(GameSession.id == uuid.UUID(session_id)).values(
                guess_started_at=func.clock_timestamp() - timedelta(seconds=seconds_ago)
            )
        )


def consume(game_client: TestClient, session_id: str, seconds_ago: float = 0) -> dict:
    response = game_client.post(f"/api/v1/game/{session_id}/glimpse")
    assert response.status_code == 200, response.text
    open_guess(session_id, seconds_ago)
    return response.json()


def wrong(game_client: TestClient, session_id: str, title: str = "Wrong Movie") -> dict:
    consume(game_client, session_id)
    response = game_client.post(f"/api/v1/game/{session_id}/guess", json={"title": title})
    assert response.status_code == 200, response.text
    return response.json()


def advance_to_round_three(game_client: TestClient, session_id: str) -> None:
    first = wrong(game_client, session_id)
    second = wrong(game_client, session_id)
    assert first["raw_applied_wrong_guess_penalty"] == "100.00"
    assert second["raw_applied_wrong_guess_penalty"] == "100.00"
    assert first["applied_wrong_guess_penalty"] == "5.00"


def test_no_scheduled_puzzle_for_today() -> None:
    response = client().post("/api/v1/game/start", json={"category": "anime"})
    assert response.status_code == 404


def test_start_resume_and_no_answer_or_hint_leaks() -> None:
    game_client = client()
    first = start(game_client)
    second = start(game_client)

    assert first["session_id"] == second["session_id"]
    assert first["current_round"] == 1
    serialized = str(first).lower()
    assert "ant-man" not in serialized
    assert "thomas incident" not in serialized
    assert "___-___" not in serialized


def test_glimpse_is_sequential_single_use_and_exposes_only_current_region() -> None:
    with SessionLocal() as session:
        expected_x = session.scalar(
            select(PuzzleStageRegion.reveal_x)
            .join(Puzzle)
            .where(Puzzle.image_key == "ant-man/ant-man.webp", PuzzleStageRegion.round_number == 1)
        )
    game_client = client()
    game = start(game_client)
    glimpse = game_client.post(f"/api/v1/game/{game['session_id']}/glimpse")
    assert glimpse.status_code == 200
    assert glimpse.json()["round_number"] == 1
    assert glimpse.json()["reveal_x"] == f"{expected_x:.2f}"
    assert "future" not in glimpse.json()
    assert "stage_regions" not in glimpse.json()
    assert game_client.post(f"/api/v1/game/{game['session_id']}/glimpse").status_code == 409


def test_guess_before_glimpse_is_rejected() -> None:
    game_client = client()
    game = start(game_client)
    assert game_client.post(f"/api/v1/game/{game['session_id']}/guess", json={"title": ANSWER}).status_code == 409


def test_hints_blocked_in_early_rounds_then_unlock_in_order_once() -> None:
    game_client = client()
    game = start(game_client)
    session_id = game["session_id"]
    assert game_client.post(f"/api/v1/game/{session_id}/hints/cryptic").status_code == 409
    advance_to_round_three(game_client, session_id)
    state = game_client.get(f"/api/v1/game/{session_id}/state").json()
    assert state["hints_available"] is True
    assert state["cryptic_hint_state"] == "available"
    assert state["title_pattern_hint_state"] == "locked"
    assert game_client.post(f"/api/v1/game/{session_id}/hints/title-pattern").status_code == 409
    cryptic = game_client.post(f"/api/v1/game/{session_id}/hints/cryptic")
    repeated = game_client.post(f"/api/v1/game/{session_id}/hints/cryptic")
    assert cryptic.json()["value"] == "The Thomas incident was greatly exaggerated."
    assert cryptic.json()["penalty"] == "2.50" and cryptic.json()["newly_unlocked"] is True
    assert repeated.json()["newly_unlocked"] is False
    pattern = game_client.post(f"/api/v1/game/{session_id}/hints/title-pattern")
    repeated_pattern = game_client.post(f"/api/v1/game/{session_id}/hints/title-pattern")
    assert pattern.json()["value"] == "___-___"
    assert pattern.json()["penalty"] == "5.00" and pattern.json()["newly_unlocked"] is True
    assert repeated_pattern.json()["newly_unlocked"] is False


@pytest.mark.parametrize("hint_count,expected", [(0, 125), (1, 150), (2, 175)])
def test_round_three_penalty_uses_hint_state_at_submission(hint_count: int, expected: int) -> None:
    game_client = client()
    session_id = start(game_client)["session_id"]
    advance_to_round_three(game_client, session_id)
    if hint_count >= 1:
        game_client.post(f"/api/v1/game/{session_id}/hints/cryptic")
    if hint_count == 2:
        game_client.post(f"/api/v1/game/{session_id}/hints/title-pattern")
    outcome = wrong(game_client, session_id)
    assert outcome["raw_applied_wrong_guess_penalty"] == f"{expected:.2f}"
    with SessionLocal() as session:
        penalties = session.execute(select(Guess.round_number, Guess.applied_wrong_guess_penalty).where(Guess.session_id == uuid.UUID(session_id)).order_by(Guess.round_number)).all()
    assert penalties[:2] == [(1, 100), (2, 100)]


@pytest.mark.parametrize("solved_round", [1, 2, 3, 4, 5])
def test_correct_answer_can_finish_every_round(solved_round: int) -> None:
    game_client = client()
    session_id = start(game_client)["session_id"]
    for _ in range(1, solved_round):
        wrong(game_client, session_id)
    consume(game_client, session_id)
    outcome = game_client.post(f"/api/v1/game/{session_id}/guess", json={"title": ANSWER})
    assert outcome.status_code == 200
    assert outcome.json()["result"]["status"] == "won"
    assert outcome.json()["result"]["solved_round"] == solved_round


def test_incorrect_round_five_is_zero_and_session_stops() -> None:
    game_client = client()
    session_id = start(game_client)["session_id"]
    for _ in range(4):
        wrong(game_client, session_id)
    final = wrong(game_client, session_id)
    assert final["result"]["status"] == "lost"
    assert final["result"]["final_score"] == "0.00"
    assert game_client.post(f"/api/v1/game/{session_id}/glimpse").status_code == 409
    assert game_client.post(f"/api/v1/game/{session_id}/hints/cryptic").status_code == 409


def test_time_penalty_and_minimum_successful_score() -> None:
    timed_client = client()
    timed_id = start(timed_client)["session_id"]
    consume(timed_client, timed_id, seconds_ago=2)
    result = timed_client.post(f"/api/v1/game/{timed_id}/guess", json={"title": ANSWER}).json()["result"]
    assert result["raw_final_score"] == "990.00"
    assert result["final_score"] == "49.50"

    floor_client = client()
    floor_id = start(floor_client)["session_id"]
    consume(floor_client, floor_id, seconds_ago=1000)
    result = floor_client.post(f"/api/v1/game/{floor_id}/guess", json={"title": ANSWER}).json()["result"]
    assert result["raw_final_score"] == "100.00"
    assert result["final_score"] == "5.00"


@pytest.mark.parametrize("submission", ["ANT MAN", " Ant--Man ", "Ant:Man", "Ant’Man"])
def test_harmless_formatting_normalizes_but_abbreviation_does_not(submission: str) -> None:
    game_client = client()
    session_id = start(game_client)["session_id"]
    consume(game_client, session_id)
    assert game_client.post(f"/api/v1/game/{session_id}/guess", json={"title": submission}).json()["correct"] is True

    abbreviation_client = client()
    abbreviation_id = start(abbreviation_client)["session_id"]
    consume(abbreviation_client, abbreviation_id)
    assert abbreviation_client.post(f"/api/v1/game/{abbreviation_id}/guess", json={"title": "Ant"}).json()["correct"] is False


def test_active_result_is_blocked_and_completed_result_reveals_answer() -> None:
    game_client = client()
    session_id = start(game_client)["session_id"]
    assert game_client.get(f"/api/v1/game/{session_id}/result").status_code == 409
    consume(game_client, session_id)
    game_client.post(f"/api/v1/game/{session_id}/guess", json={"title": ANSWER})
    result = game_client.get(f"/api/v1/game/{session_id}/result")
    assert result.status_code == 200
    assert result.json()["canonical_movie_title"] == ANSWER


def test_concurrent_duplicate_guess_only_records_once() -> None:
    original = client()
    session_id = start(original)["session_id"]
    consume(original, session_id)
    cookie = original.cookies.get("framebyframe_guest")

    def submit():
        worker = client()
        worker.cookies.set("framebyframe_guest", cookie)
        return worker.post(f"/api/v1/game/{session_id}/guess", json={"title": "Wrong"}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: submit(), range(2)))
    assert sorted(statuses) == [200, 409]
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Guess).where(Guess.session_id == uuid.UUID(session_id), Guess.round_number == 1)) == 1


@pytest.mark.parametrize(
    "utc_now,expected_game_date,category_slug",
    [
        (datetime(2030, 1, 1, 18, 0, tzinfo=timezone.utc), datetime(2030, 1, 1).date(), "anime"),
        (datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc), datetime(2030, 1, 2).date(), "superheroes"),
    ],
)
def test_daily_selection_uses_game_timezone_across_utc_midnight(
    utc_now: datetime, expected_game_date, category_slug: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with SessionLocal.begin() as session:
        category = session.scalar(select(Category).where(Category.slug == category_slug))
        rules = session.scalar(select(RuleSet).where(RuleSet.name == "Daily gameplay v1"))
        puzzle = session.scalar(select(Puzzle).where(Puzzle.image_key == "ant-man/ant-man.webp"))
        daily = session.scalar(select(DailyPuzzle).where(
            DailyPuzzle.category_id == category.id,
            DailyPuzzle.puzzle_date == expected_game_date,
            DailyPuzzle.status == PublicationStatus.PUBLISHED,
        ))
        if daily is None:
            daily = DailyPuzzle(
                puzzle_id=puzzle.id, category_id=category.id, rule_set_id=rules.id,
                puzzle_date=expected_game_date, status=PublicationStatus.PUBLISHED,
            )
            session.add(daily)

    monkeypatch.setattr(GameplayService, "now", lambda self: utc_now)
    with SessionLocal() as session:
        game = GameplayService(GameRepository(session), "Asia/Kolkata").start(category_slug, uuid.uuid4())
        assert game.daily_puzzle.puzzle_date == expected_game_date


def test_gameplay_never_mutates_saved_puzzle_regions() -> None:
    with SessionLocal() as session:
        puzzle_id = session.scalar(select(Puzzle.id).where(Puzzle.image_key == "ant-man/ant-man.webp"))
        before = session.execute(
            select(PuzzleStageRegion.round_number, PuzzleStageRegion.reveal_x, PuzzleStageRegion.reveal_y)
            .where(PuzzleStageRegion.puzzle_id == puzzle_id)
            .order_by(PuzzleStageRegion.round_number)
        ).all()

    game_client = client()
    session_id = start(game_client)["session_id"]
    wrong(game_client, session_id)

    with SessionLocal() as session:
        after = session.execute(
            select(PuzzleStageRegion.round_number, PuzzleStageRegion.reveal_x, PuzzleStageRegion.reveal_y)
            .where(PuzzleStageRegion.puzzle_id == puzzle_id)
            .order_by(PuzzleStageRegion.round_number)
        ).all()
    assert after == before
