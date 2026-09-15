from __future__ import annotations

import uuid
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, select

from backend.app.api.dependencies import get_asset_storage
from backend.app.db.session import SessionLocal
from backend.app.main import create_app
from backend.app.models.entities import (
    AlbumnesiaAttempt, AlbumnesiaContent, AlbumnesiaDailyProgress, AlbumnesiaGameRound,
    AlbumnesiaGameSet, AlbumnesiaParticipant, AlbumnesiaRoundSubmission, ContentEntry,
)
from backend.app.storage import LocalFilesystemStorage


@pytest.fixture
def album_client(tmp_path: Path):
    source_assets = Path("assets/scenes")
    if source_assets.exists():
        for source in source_assets.rglob("*"):
            if source.is_file():
                destination = tmp_path / source.relative_to(source_assets)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    storage = LocalFilesystemStorage(tmp_path)
    ids: list[uuid.UUID] = []
    tracked = (AlbumnesiaAttempt, AlbumnesiaParticipant, AlbumnesiaGameSet, AlbumnesiaDailyProgress)
    with SessionLocal() as session:
        originals = {
            model: set(session.scalars(select(model.id if hasattr(model, "id") else model.guest_id)))
            for model in tracked
        }
    for number in range(1, 6):
        directory = tmp_path / f"album-{number}"
        directory.mkdir()
        Image.new("RGB", (80, 80), (number * 30, 50, 100)).save(directory / "cover.webp")
    with SessionLocal.begin() as session:
        for number in range(1, 6):
            entry = ContentEntry(
                category="albumnesia", primary_answer=f"Test Album {number}",
                alternative_answers=[f"Album {number}"], image_key=f"album-{number}/cover.webp",
                difficulty=number, is_active=True,
                albumnesia=AlbumnesiaContent(
                    artist=f"Secret Artist {number}", release_year=1990 + number,
                    recognizable_track=f"Track {number}", artist_initials=f"SA{number}",
                    enabled_distortions=["pixel_hangover", "channel_damage"],
                    text_mask_regions=[], subject_mask_regions=[],
                ),
            )
            session.add(entry); session.flush(); ids.append(entry.id)
    app = create_app(); app.dependency_overrides[get_asset_storage] = lambda: storage
    with TestClient(app) as client:
        yield client
    with SessionLocal.begin() as session:
        # Game round snapshots SET NULL when source albums are removed. Remove
        # test-created sets explicitly before deleting their catalogue rows.
        test_set_ids = list(session.scalars(select(AlbumnesiaGameSet.id).join(AlbumnesiaGameSet.rounds).where(
            AlbumnesiaGameRound.content_id.in_(ids)
        )))
        if test_set_ids:
            session.execute(delete(AlbumnesiaGameSet).where(AlbumnesiaGameSet.id.in_(test_set_ids)))
        session.execute(delete(AlbumnesiaAttempt).where(AlbumnesiaAttempt.id.not_in(originals[AlbumnesiaAttempt])))
        session.execute(delete(AlbumnesiaParticipant).where(AlbumnesiaParticipant.id.not_in(originals[AlbumnesiaParticipant])))
        session.execute(delete(AlbumnesiaGameSet).where(AlbumnesiaGameSet.id.not_in(originals[AlbumnesiaGameSet])))
        session.execute(delete(AlbumnesiaDailyProgress).where(AlbumnesiaDailyProgress.guest_id.not_in(originals[AlbumnesiaDailyProgress])))
        session.execute(delete(ContentEntry).where(ContentEntry.id.in_(ids)))


def test_daily_is_deterministic_private_and_one_attempt(album_client: TestClient) -> None:
    first = album_client.post("/api/v1/albumnesia/daily/start")
    assert first.status_code == 200, first.text
    state = first.json()
    assert state["phase"] == "ready"
    assert state["total_rounds"] == 1 and state["max_score"] == "10.00"
    assert state["clues"] is None and state["revealed_title"] is None
    assert state["image_url"].startswith("/api/v1/albumnesia/attempts/")
    cover = album_client.get(state["image_url"])
    assert cover.status_code == 200, cover.text
    assert cover.headers["content-type"] == "image/webp"
    resumed = album_client.post("/api/v1/albumnesia/daily/start").json()
    assert resumed["attempt_id"] == state["attempt_id"]


def test_memorize_guess_and_decimal_server_score(album_client: TestClient) -> None:
    state = album_client.post("/api/v1/albumnesia/daily/start").json()
    started = album_client.post(f"/api/v1/albumnesia/attempts/{state['attempt_id']}/ready")
    assert started.status_code == 200
    assert started.json()["phase"] == "memorize"
    assert set(started.json()["clues"]) == {"artist_initials", "release_year", "recognizable_track"}
    with SessionLocal.begin() as session:
        attempt = session.get(AlbumnesiaAttempt, uuid.UUID(state["attempt_id"]))
        title = attempt.game_set.rounds[0].title_snapshot
        attempt.phase_deadline -= timedelta(seconds=5)
    guessing = album_client.get(f"/api/v1/albumnesia/attempts/{state['attempt_id']}").json()
    assert guessing["phase"] == "guess" and guessing["image_url"] is None and guessing["clues"] is None
    answered = album_client.post(f"/api/v1/albumnesia/attempts/{state['attempt_id']}/submit", json={"title": title})
    assert answered.status_code == 200
    assert answered.json()["last_correct"] is True
    assert 8 <= float(answered.json()["last_score"]) <= 10
    duplicate = album_client.post(f"/api/v1/albumnesia/attempts/{state['attempt_id']}/submit", json={"title": title})
    assert duplicate.status_code == 200
    assert duplicate.json()["last_score"] == answered.json()["last_score"]
    with SessionLocal() as session:
        stored = session.scalar(select(AlbumnesiaRoundSubmission).where(AlbumnesiaRoundSubmission.attempt_id == uuid.UUID(state["attempt_id"])))
        assert stored.awarded_score.as_tuple().exponent == -2


def test_title_search_never_exposes_artist_or_cover(album_client: TestClient) -> None:
    response = album_client.get("/api/v1/albumnesia/titles", params={"q": "Test Album"})
    assert response.status_code == 200
    assert response.json() == [f"Test Album {number}" for number in range(1, 6)]
    assert "Secret Artist" not in response.text and "cover.webp" not in response.text


def test_room_uses_shared_snapshot_and_hides_partial_leaderboard(album_client: TestClient) -> None:
    room = album_client.post("/api/v1/albumnesia/rooms", json={"room_name": "Needle Club", "display_name": "Ada"})
    assert room.status_code == 201, room.text
    details = room.json()
    assert details["joined"] is True and details["attempt_id"] is None
    assert details["host_name"] == "Ada"
    board = album_client.get(f"/api/v1/albumnesia/rooms/{details['code']}/leaderboard").json()
    assert board["entries"] == [{"display_name": "Ada", "finished": False, "correct_count": None,
                                  "score": None, "answer_time_ms": None, "average_response_ms": None,
                                  "completed_at": None, "is_current": True}]


def test_backend_timeout_records_zero_and_removes_cover(album_client: TestClient) -> None:
    state = album_client.post("/api/v1/albumnesia/daily/start").json()
    album_client.post(f"/api/v1/albumnesia/attempts/{state['attempt_id']}/ready")
    with SessionLocal.begin() as session:
        attempt = session.get(AlbumnesiaAttempt, uuid.UUID(state["attempt_id"])); attempt.phase_deadline -= timedelta(seconds=11)
    timed_out = album_client.get(f"/api/v1/albumnesia/attempts/{state['attempt_id']}").json()
    assert timed_out["phase"] == "feedback" and timed_out["last_correct"] is False
    assert timed_out["last_score"] == "0.00" and timed_out["image_url"] is None


def test_single_daily_album_completion_increments_streak_idempotently(album_client: TestClient) -> None:
    state = album_client.post("/api/v1/albumnesia/daily/start").json()
    attempt_id = state["attempt_id"]
    started = album_client.post(f"/api/v1/albumnesia/attempts/{attempt_id}/ready")
    assert started.status_code == 200, started.text
    with SessionLocal.begin() as session:
        attempt = session.get(AlbumnesiaAttempt, uuid.UUID(attempt_id))
        title = attempt.game_set.rounds[0].title_snapshot
        attempt.phase_deadline -= timedelta(seconds=5)
    assert album_client.get(f"/api/v1/albumnesia/attempts/{attempt_id}").json()["phase"] == "guess"
    submitted = album_client.post(f"/api/v1/albumnesia/attempts/{attempt_id}/submit", json={"title": title})
    assert submitted.status_code == 200, submitted.text
    assert 8 <= float(submitted.json()["last_score"]) <= 10
    duplicate = album_client.post(f"/api/v1/albumnesia/attempts/{attempt_id}/submit", json={"title": title})
    assert duplicate.status_code == 200, duplicate.text
    with SessionLocal.begin() as session:
        attempt = session.get(AlbumnesiaAttempt, uuid.UUID(attempt_id))
        attempt.phase_deadline = datetime.now(timezone.utc) - timedelta(milliseconds=1)
    state = album_client.get(f"/api/v1/albumnesia/attempts/{attempt_id}").json()
    assert state["status"] == "completed" and state["phase"] == "results"
    assert state["correct_count"] == 1 and state["streak"] == 1
    assert 8 <= float(state["total_score"]) <= 10
    assert state["max_score"] == "10.00" and len(state["results"]) == 1
    final_retry = album_client.post(f"/api/v1/albumnesia/attempts/{attempt_id}/submit", json={"title": title})
    assert final_retry.status_code == 200
    assert final_retry.json()["status"] == "completed"


def test_failed_single_album_daily_resets_streak(album_client: TestClient) -> None:
    state = album_client.post("/api/v1/albumnesia/daily/start").json()
    attempt_id = uuid.UUID(state["attempt_id"])
    with SessionLocal.begin() as session:
        attempt = session.get(AlbumnesiaAttempt, attempt_id)
        session.add(AlbumnesiaDailyProgress(
            guest_id=attempt.guest_id, current_streak=3, longest_streak=3,
            last_completed_date=attempt.game_set.game_date - timedelta(days=1),
        ))
    album_client.post(f"/api/v1/albumnesia/attempts/{attempt_id}/ready")
    with SessionLocal.begin() as session:
        attempt = session.get(AlbumnesiaAttempt, attempt_id)
        attempt.phase_deadline = datetime.now(timezone.utc) - timedelta(seconds=11)
    feedback = album_client.get(f"/api/v1/albumnesia/attempts/{attempt_id}").json()
    assert feedback["phase"] == "feedback" and feedback["last_correct"] is False
    with SessionLocal.begin() as session:
        attempt = session.get(AlbumnesiaAttempt, attempt_id)
        attempt.phase_deadline = datetime.now(timezone.utc) - timedelta(milliseconds=1)
    result = album_client.get(f"/api/v1/albumnesia/attempts/{attempt_id}").json()
    assert result["status"] == "completed" and result["correct_count"] == 0
    assert result["total_score"] == "0.00" and result["streak"] == 0


def test_last_moment_correct_answer_is_worth_about_eight(album_client: TestClient) -> None:
    state = album_client.post("/api/v1/albumnesia/daily/start").json()
    attempt_id = state["attempt_id"]
    album_client.post(f"/api/v1/albumnesia/attempts/{attempt_id}/ready")
    with SessionLocal.begin() as session:
        attempt = session.get(AlbumnesiaAttempt, uuid.UUID(attempt_id))
        title = attempt.game_set.rounds[0].title_snapshot
        attempt.phase = "guess"
        attempt.phase_deadline = datetime.now(timezone.utc) + timedelta(milliseconds=150)
    result = album_client.post(f"/api/v1/albumnesia/attempts/{attempt_id}/submit", json={"title": title})
    assert result.status_code == 200
    assert 8 <= float(result.json()["last_score"]) <= 8.10


def test_host_and_joiner_continue_separately_with_identical_room_snapshot(album_client: TestClient) -> None:
    created = album_client.post("/api/v1/albumnesia/rooms", json={"room_name": "Weekend Vinyl Wars", "display_name": "Ashish"}).json()
    code = created["code"]
    host_token = album_client.cookies.get("framebyframe_guest")
    host_state = album_client.post(f"/api/v1/albumnesia/rooms/{code}/continue").json()
    assert host_state["phase"] == "ready"

    album_client.cookies.clear()
    invitation = album_client.get(f"/api/v1/albumnesia/rooms/{code}").json()
    assert invitation["joined"] is False and invitation["host_name"] == "Ashish"
    joined = album_client.post(f"/api/v1/albumnesia/rooms/{code}/join", json={"display_name": "Maya"}).json()
    assert joined["joined"] is True and joined["attempt_id"] is None
    guest_state = album_client.post(f"/api/v1/albumnesia/rooms/{code}/continue").json()
    assert guest_state["phase"] == "ready"
    assert (guest_state["distortion"], guest_state["distortion_seed"]) == (host_state["distortion"], host_state["distortion_seed"])

    album_client.cookies.clear(); album_client.cookies.set("framebyframe_guest", host_token)
    resumed = album_client.post(f"/api/v1/albumnesia/rooms/{code}/continue").json()
    assert resumed["attempt_id"] == host_state["attempt_id"]
