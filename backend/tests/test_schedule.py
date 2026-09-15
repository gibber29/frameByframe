from datetime import date, timedelta
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from backend.app.db.session import SessionLocal
from backend.app.main import create_app
from backend.app.models.entities import ContentStatus, DailyPuzzle, Movie, Puzzle, PuzzleStageRegion, RevealProfile


from backend.app.core.config import settings

client = TestClient(create_app(), headers={"X-Admin-Token": settings.admin_token})


def create_test_puzzle(title: str, status: ContentStatus) -> uuid.UUID:
    with SessionLocal.begin() as session:
        movie = session.scalar(select(Movie).where(Movie.title == title))
        profile = session.scalar(select(RevealProfile).where(RevealProfile.name == "Default five-turn reveal"))
        puzzle = Puzzle(
            movie_id=movie.id, image_key=f"schedule-tests/{uuid.uuid4().hex}.webp", cryptic_hint="Schedule test hint",
            difficulty=2, reveal_profile_id=profile.id, status=status,
            stage_regions=[PuzzleStageRegion(round_number=n, reveal_x=40, reveal_y=40) for n in range(1, 5)],
        )
        session.add(puzzle)
        session.flush()
        return puzzle.id


def options() -> dict:
    response = client.get("/api/v1/admin/schedule")
    assert response.status_code == 200, response.text
    return response.json()


def test_daily_schedule_crud_constraints_and_puzzle_preservation() -> None:
    ready = create_test_puzzle("Avengers: Endgame", ContentStatus.READY)
    draft = create_test_puzzle("Avengers: Infinity War", ContentStatus.DRAFT)
    data = options()
    anime = next(category for category in data["playable_categories"] if category["slug"] == "anime")
    rules = next(rule for rule in data["rule_sets"] if rule["name"] == "Daily gameplay v1")
    schedule_date = date.today() + timedelta(days=1000 + ready.int % 10000)

    schedule = None
    try:
        draft_response = client.post("/api/v1/admin/schedule", json={
            "puzzle_id": str(draft), "category_id": anime["id"], "rule_set_id": rules["id"],
            "puzzle_date": schedule_date.isoformat(), "status": "published",
        })
        assert draft_response.status_code == 422

        created = client.post("/api/v1/admin/schedule", json={
            "puzzle_id": str(ready), "category_id": anime["id"],
            "puzzle_date": schedule_date.isoformat(), "status": "scheduled",
        })
        assert created.status_code == 201, created.text
        schedule = created.json()
        assert schedule["rule_set_name"] == "Daily gameplay v2"
        duplicate = client.post("/api/v1/admin/schedule", json={
            "puzzle_id": str(ready), "category_id": anime["id"], "rule_set_id": rules["id"],
            "puzzle_date": schedule_date.isoformat(), "status": "published",
        })
        assert duplicate.status_code == 409
        published = client.patch(f"/api/v1/admin/schedule/{schedule['id']}", json={"status": "published"})
        assert published.status_code == 200 and published.json()["status"] == "published"
        deleted = client.delete(f"/api/v1/admin/schedule/{schedule['id']}")
        assert deleted.status_code == 204
        schedule = None
        with SessionLocal() as session:
            assert session.get(Puzzle, ready) is not None
    finally:
        if schedule:
            client.delete(f"/api/v1/admin/schedule/{schedule['id']}")
        with SessionLocal.begin() as session:
            session.execute(delete(Puzzle).where(Puzzle.id.in_((ready, draft))))
