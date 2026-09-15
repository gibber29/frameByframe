import uuid
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from backend.app.api.dependencies import get_asset_storage
from backend.app.api.v1.routes.admin import _upload_windows
from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.main import create_app
from backend.app.models.entities import Category, Movie, MovieCategory, Puzzle, RevealProfile
from backend.app.repositories.puzzles import PuzzleRepository
from backend.app.schemas.admin import CompletePuzzleWrite
from backend.app.services.puzzle_authoring import AuthoringValidationError, PuzzleAuthoringService, slugify
from backend.app.storage import LocalFilesystemStorage


def encoded_image(format_name: str = "PNG", size: tuple[int, int] = (48, 30)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "#173d6b").save(output, format=format_name)
    return output.getvalue()


@pytest.fixture
def wizard(tmp_path: Path):
    storage = LocalFilesystemStorage(tmp_path)
    app = create_app()
    app.dependency_overrides[get_asset_storage] = lambda: storage
    _upload_windows.clear()
    with TestClient(app, headers={"X-Admin-Token": settings.admin_token}) as client:
        yield client, storage


def stage(client: TestClient, format_name: str = "PNG", filename: str = "Scene upload.png") -> dict:
    response = client.post(
        "/api/v1/admin/uploads",
        files={"image": (filename, encoded_image(format_name), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def options(client: TestClient) -> tuple[dict, dict, dict]:
    movies = client.get("/api/v1/movies").json()
    classifications = client.get("/api/v1/admin/classifications").json()
    profile = client.get("/api/v1/admin/assets").json()["reveal_profiles"][0]
    return movies, classifications, profile


def complete_payload(client: TestClient, upload: dict, *, ready: bool = True) -> dict:
    movies, classifications, profile = options(client)
    ant_man = next(movie for movie in movies if movie["title"] == "Ant-Man")
    superheroes = next(item for item in classifications["playable_categories"] if item["slug"] == "superheroes")
    marvel = next(item for item in classifications["tags"] if item["slug"] == "marvel")
    return {
        "staged_upload_id": upload["stage_id"],
        "existing_movie_id": ant_man["id"],
        "category_ids": [superheroes["id"]],
        "tag_ids": [marvel["id"]],
        "stage_regions": [
            {"round_number": number, "reveal_x": 10 + number, "reveal_y": 80 - number}
            for number in range(1, 5)
        ] if ready else [{"round_number": 1, "reveal_x": 11, "reveal_y": 79}],
        "cryptic_hint": "A staged test clue.",
        "difficulty": 4,
        "reveal_profile_id": profile["id"],
        "status": "ready" if ready else "draft",
    }


def remove_puzzle(puzzle_id: str, storage: LocalFilesystemStorage, image_key: str) -> None:
    with SessionLocal.begin() as session:
        session.execute(delete(Puzzle).where(Puzzle.id == uuid.UUID(puzzle_id)))
    storage.delete(image_key)


def test_successful_complete_creation_reuses_movie_and_assigns_multiple_categories_and_tag(wizard) -> None:
    client, storage = wizard
    upload = stage(client)
    payload = complete_payload(client, upload)
    _, classifications, _ = options(client)
    all_time = next(item for item in classifications["playable_categories"] if item["slug"] == "all-time-greats")
    payload["category_ids"].append(all_time["id"])
    response = client.post("/api/v1/admin/puzzles/complete", json=payload)
    assert response.status_code == 201, response.text
    puzzle = response.json()
    try:
        assert puzzle["movie_id"] == payload["existing_movie_id"]
        assert set(puzzle["category_ids"]) == set(payload["category_ids"])
        assert set(payload["tag_ids"]).issubset(puzzle["tag_ids"])
        assert puzzle["status"] == "ready"
        assert len(puzzle["stage_regions"]) == 4
        assert puzzle["image_key"].startswith("ant-man/")
        assert puzzle["image_key"].endswith(".webp")
        assert "Scene upload" not in puzzle["image_key"]
        assert storage.exists(puzzle["image_key"])
        assert client.get(puzzle["image_url"]).headers["content-type"] == "image/webp"
    finally:
        remove_puzzle(puzzle["id"], storage, puzzle["image_key"])
        with SessionLocal.begin() as session:
            session.execute(delete(MovieCategory).where(
                MovieCategory.movie_id == uuid.UUID(payload["existing_movie_id"]),
                MovieCategory.category_id == uuid.UUID(payload["category_ids"][1]),
            ))


def test_new_movie_is_created_on_final_save_with_generated_slug(wizard) -> None:
    client, storage = wizard
    upload = stage(client, "JPEG", "My Original.JPG")
    payload = complete_payload(client, upload, ready=False)
    payload.pop("existing_movie_id")
    title = f"Wizard Café {uuid.uuid4().hex[:8]}"
    payload["new_movie"] = {"title": title, "release_year": 2025, "media_type": "movie"}
    response = client.post("/api/v1/admin/puzzles/complete", json=payload)
    assert response.status_code == 201, response.text
    puzzle = response.json()
    movie_id = uuid.UUID(puzzle["movie_id"])
    try:
        assert puzzle["image_key"].startswith(f"{slugify(title)}/")
        assert puzzle["status"] == "draft"
        with SessionLocal() as session:
            movie = session.get(Movie, movie_id)
            assert movie is not None
            assert movie.normalized_title
    finally:
        remove_puzzle(puzzle["id"], storage, puzzle["image_key"])
        with SessionLocal.begin() as session:
            session.execute(delete(Movie).where(Movie.id == movie_id))


def test_duplicate_new_movie_is_rejected_and_staged_file_is_cleaned(wizard) -> None:
    client, storage = wizard
    upload = stage(client)
    payload = complete_payload(client, upload, ready=False)
    payload.pop("existing_movie_id")
    payload["new_movie"] = {"title": "  ANT—MAN ", "release_year": 2015, "media_type": "movie"}
    response = client.post("/api/v1/admin/puzzles/complete", json=payload)
    assert response.status_code == 409
    assert not storage._stage_path(upload["stage_id"]).exists()


def test_draft_allows_incomplete_regions_but_ready_does_not(wizard) -> None:
    client, storage = wizard
    draft_upload = stage(client)
    draft_payload = complete_payload(client, draft_upload, ready=False)
    draft = client.post("/api/v1/admin/puzzles/complete", json=draft_payload)
    assert draft.status_code == 201, draft.text
    puzzle = draft.json()
    remove_puzzle(puzzle["id"], storage, puzzle["image_key"])

    ready_upload = stage(client)
    invalid = complete_payload(client, ready_upload)
    invalid["stage_regions"] = invalid["stage_regions"][:3]
    response = client.post("/api/v1/admin/puzzles/complete", json=invalid)
    assert response.status_code == 422
    assert not storage._stage_path(ready_upload["stage_id"]).exists()


def test_metadata_update_and_image_replacement_use_staged_storage(wizard) -> None:
    client, storage = wizard
    created = client.post(
        "/api/v1/admin/puzzles/complete",
        json=complete_payload(client, stage(client), ready=False),
    )
    assert created.status_code == 201, created.text
    puzzle = created.json()
    old_key = puzzle["image_key"]
    try:
        patched = client.patch(
            f"/api/v1/admin/puzzles/{puzzle['id']}",
            json={"cryptic_hint": "Updated safely", "difficulty": 2},
        )
        assert patched.status_code == 200
        assert patched.json()["cryptic_hint"] == "Updated safely"
        replacement = stage(client, "JPEG", "replacement.jpg")
        replaced = client.post(
            f"/api/v1/admin/puzzles/{puzzle['id']}/image",
            json={"staged_upload_id": replacement["stage_id"]},
        )
        assert replaced.status_code == 200, replaced.text
        puzzle = replaced.json()
        assert puzzle["image_key"] != old_key
        assert not storage.exists(old_key)
        assert storage.exists(puzzle["image_key"])
    finally:
        remove_puzzle(puzzle["id"], storage, puzzle["image_key"])


def test_cancelled_upload_and_path_traversal_leave_no_staged_file(wizard) -> None:
    client, storage = wizard
    upload = stage(client)
    assert client.get(upload["image_url"]).status_code == 200
    assert client.delete(f"/api/v1/admin/uploads/{upload['stage_id']}").status_code == 204
    assert not storage._stage_path(upload["stage_id"]).exists()
    assert client.get("/api/v1/admin/uploads/../../secret/image").status_code in {404, 422}


def test_fake_extension_and_upload_size_are_rejected(wizard, monkeypatch) -> None:
    client, _ = wizard
    fake = client.post("/api/v1/admin/uploads", files={"image": ("fake.png", b"not an image", "image/png")})
    assert fake.status_code == 422
    from backend.app.api.v1.routes import admin
    monkeypatch.setattr(admin.settings, "upload_max_bytes", 10)
    too_large = client.post("/api/v1/admin/uploads", files={"image": ("large.png", encoded_image(), "image/png")})
    assert too_large.status_code == 413


def test_upload_rate_limit_is_enforced(wizard, monkeypatch) -> None:
    client, storage = wizard
    from backend.app.api.v1.routes import admin
    monkeypatch.setattr(admin.settings, "upload_rate_limit_per_minute", 2)
    uploads = [stage(client), stage(client)]
    limited = client.post(
        "/api/v1/admin/uploads",
        files={"image": ("third.png", encoded_image(), "image/png")},
    )
    assert limited.status_code == 429
    for upload in uploads:
        storage.delete_staged(upload["stage_id"])


def test_dynamic_tag_creation_and_admin_disabled_mutations(wizard) -> None:
    client, _ = wizard
    name = f"Future Tag {uuid.uuid4().hex[:8]}"
    response = client.post("/api/v1/admin/tags", json={"name": name})
    assert response.status_code == 201
    tag = response.json()
    try:
        assert tag["is_playable"] is False
        assert tag["slug"] == slugify(name)
    finally:
        with SessionLocal.begin() as session:
            session.execute(delete(Category).where(Category.id == uuid.UUID(tag["id"])))

    from backend.app.core.config import Settings, settings
    disabled = TestClient(create_app(Settings(DATABASE_URL=settings.database_url, ADMIN_ENABLED=False)))
    assert disabled.post("/api/v1/admin/uploads", files={"image": ("x.png", encoded_image(), "image/png")}).status_code == 404
    assert disabled.post("/api/v1/admin/tags", json={"name": "Forbidden"}).status_code == 404


def test_admin_mutation_rejects_missing_credentials(wizard) -> None:
    client, _ = wizard
    unauthorized = TestClient(client.app)
    response = unauthorized.post(
        "/api/v1/admin/uploads",
        files={"image": ("scene.png", encoded_image(), "image/png")},
    )
    assert response.status_code == 401


def service_payload(stage_id: str, movie_id: uuid.UUID, profile_id: uuid.UUID) -> CompletePuzzleWrite:
    return CompletePuzzleWrite(
        staged_upload_id=stage_id, existing_movie_id=movie_id,
        cryptic_hint="Transaction clue", difficulty=3, reveal_profile_id=profile_id,
        stage_regions=[], status="draft",
    )


def test_failed_database_transaction_compensates_finalized_file(tmp_path: Path, monkeypatch) -> None:
    storage = LocalFilesystemStorage(tmp_path)
    staged = storage.save_staged(BytesIO(encoded_image()), "source.png", 100_000, 85)
    with SessionLocal() as session:
        movie_id = session.scalar(select(Movie.id).where(Movie.title == "Ant-Man"))
        profile_id = session.scalar(select(RevealProfile.id).limit(1))
        service = PuzzleAuthoringService(PuzzleRepository(session), storage)
        monkeypatch.setattr(session, "commit", lambda: (_ for _ in ()).throw(IntegrityError("commit", {}, Exception())))
        with pytest.raises(Exception):
            service.create_complete(service_payload(staged.stage_id, movie_id, profile_id))
    assert not list(tmp_path.glob("ant-man/*.webp"))
    assert not storage._stage_path(staged.stage_id).exists()


def test_failed_final_file_movement_rolls_back_and_cleans_stage(tmp_path: Path, monkeypatch) -> None:
    storage = LocalFilesystemStorage(tmp_path)
    staged = storage.save_staged(BytesIO(encoded_image()), "source.png", 100_000, 85)
    with SessionLocal() as session:
        movie_id = session.scalar(select(Movie.id).where(Movie.title == "Ant-Man"))
        profile_id = session.scalar(select(RevealProfile.id).limit(1))
        service = PuzzleAuthoringService(PuzzleRepository(session), storage)
        monkeypatch.setattr(storage, "finalize", lambda *_: (_ for _ in ()).throw(OSError("disk unavailable")))
        with pytest.raises(AuthoringValidationError):
            service.create_complete(service_payload(staged.stage_id, movie_id, profile_id))
    assert not storage._stage_path(staged.stage_id).exists()


def puzzle_snapshot() -> tuple[int, str | None]:
    with SessionLocal() as session:
        return (
            session.scalar(select(func.count()).select_from(Puzzle)),
            session.scalar(text("""
                SELECT md5(string_agg(puzzle_id::text || ':' || round_number || ':' || reveal_x || ':' || reveal_y,
                                      '|' ORDER BY puzzle_id, round_number))
                FROM framebyframe.puzzle_stage_regions
            """)),
        )


@pytest.fixture(scope="module", autouse=True)
def preserve_existing_puzzles():
    before = puzzle_snapshot()
    yield
    assert puzzle_snapshot() == before
