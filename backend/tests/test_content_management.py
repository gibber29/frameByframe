import hashlib
import uuid
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select, text

from backend.app.api.dependencies import get_asset_storage
from backend.app.api.v1.routes.admin import _upload_windows
from backend.app.core.config import Settings, settings
from backend.app.db.session import SessionLocal
from backend.app.main import create_app
from backend.app.models.entities import ContentEntry, Movie, Puzzle
from backend.app.schemas.content import ALL_DISTORTIONS
from backend.app.storage import LocalFilesystemStorage


def iconic_snapshot() -> tuple[int, int, int, str | None]:
    with SessionLocal() as session:
        return (
            session.scalar(select(func.count()).select_from(Movie)),
            session.scalar(select(func.count()).select_from(Puzzle)),
            session.scalar(select(func.count()).select_from(ContentEntry)),
            session.scalar(text("""
                SELECT md5(string_agg(puzzle_id::text || ':' || round_number || ':' || reveal_x || ':' || reveal_y,
                                      '|' ORDER BY puzzle_id, round_number))
                FROM framebyframe.puzzle_stage_regions
            """)),
        )


@pytest.fixture(scope="module", autouse=True)
def preserve_iconic_content():
    before = iconic_snapshot()
    yield
    assert iconic_snapshot() == before


def image_bytes(colour: str = "#1e4976", image_format: str = "PNG") -> bytes:
    stream = BytesIO()
    Image.new("RGB", (72, 72), colour).save(stream, format=image_format)
    return stream.getvalue()


@pytest.fixture
def content_client(tmp_path: Path):
    storage = LocalFilesystemStorage(tmp_path)
    app = create_app()
    app.dependency_overrides[get_asset_storage] = lambda: storage
    _upload_windows.clear()
    with TestClient(app, headers={"X-Admin-Token": settings.admin_token}) as client:
        yield client, storage


def stage(client: TestClient, colour: str = "#1e4976") -> dict:
    response = client.post(
        "/api/v1/admin/uploads",
        files={"image": ("original cover.png", image_bytes(colour), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def unique_answer(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def delete_if_present(client: TestClient, content_id: str | None) -> None:
    if content_id:
        client.delete(f"/api/v1/admin/content/{content_id}")


def test_badly_explained_complete_admin_lifecycle_preserves_clue_order(content_client) -> None:
    client, storage = content_client
    title = unique_answer("Bad explanation")
    clues = ["Cryptic first", "Niche second", "Recognisable third", "Giveaway fourth"]
    created_id = duplicate_id = None
    try:
        created = client.post("/api/v1/admin/content/badly-explained", json={
            "title": title,
            "clues": clues,
            "alternative_answers": [f"{title} alt"],
            "difficulty": 4,
            "is_active": True,
            "staged_upload_id": stage(client)["stage_id"],
        })
        assert created.status_code == 201, created.text
        item = created.json()
        created_id = item["id"]
        assert item["clues"] == clues
        assert item["is_active"] is True
        assert item["image_url"].startswith("/api/v1/admin/content/")
        assert client.get(item["image_url"]).headers["content-type"] == "image/webp"

        reordered = ["Cryptic edited", "Niche edited", "Recognisable edited", "Giveaway edited"]
        updated = client.patch(
            f"/api/v1/admin/content/{created_id}/badly-explained",
            json={"clues": reordered},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["clues"] == reordered

        conflict = client.get("/api/v1/admin/content/check-answer", params={
            "category": "badly_explained", "answer": f"  {title.upper()}  ",
        })
        assert conflict.json() == {"duplicate": True, "conflicting_title": title}
        duplicate_create = client.post("/api/v1/admin/content/badly-explained", json={
            "title": unique_answer("Different"), "clues": clues,
            "alternative_answers": [title], "difficulty": 2, "is_active": False,
            "staged_upload_id": stage(client, "#cc3344")["stage_id"],
        })
        assert duplicate_create.status_code == 409

        duplicated = client.post(f"/api/v1/admin/content/{created_id}/duplicate", json={
            "primary_answer": unique_answer("Bad explanation copy"),
        })
        assert duplicated.status_code == 201, duplicated.text
        duplicate_id = duplicated.json()["id"]
        assert duplicated.json()["is_active"] is False
        assert duplicated.json()["clues"] == reordered
        assert duplicated.json()["image_url"] != item["image_url"]

        listing = client.get("/api/v1/admin/content", params={
            "search": title, "category": "badly_explained", "difficulty": 4,
            "is_active": True,
        })
        assert [entry["id"] for entry in listing.json()] == [created_id]
    finally:
        delete_if_present(client, duplicate_id)
        delete_if_present(client, created_id)
        for staged_path in storage.staging_root.glob("*.webp") if storage.staging_root.exists() else []:
            staged_path.unlink()


def test_badly_explained_rejects_incomplete_clues_and_null_patch(content_client) -> None:
    client, storage = content_client
    upload = stage(client)
    invalid = client.post("/api/v1/admin/content/badly-explained", json={
        "title": unique_answer("Incomplete"), "clues": ["one", "two", "three"],
        "alternative_answers": [], "difficulty": 3, "is_active": True,
        "staged_upload_id": upload["stage_id"],
    })
    assert invalid.status_code == 422
    assert storage.staged_path(upload["stage_id"]).is_file()

    missing_image = client.post("/api/v1/admin/content/badly-explained", json={
        "title": unique_answer("Missing image"), "clues": ["one", "two", "three", "four"],
        "alternative_answers": [], "difficulty": 3, "is_active": False,
        "staged_upload_id": str(uuid.uuid4()),
    })
    assert missing_image.status_code == 422
    storage.delete_staged(upload["stage_id"])


def test_albumnesia_settings_masks_and_original_image_persist(content_client) -> None:
    client, storage = content_client
    title = unique_answer("Test album")
    content_id = None
    upload = stage(client, "#6b3fa0")
    staged_digest = hashlib.sha256(storage.staged_path(upload["stage_id"]).read_bytes()).hexdigest()
    rectangle = {"kind": "rectangle", "points": [{"x": .1025, "y": .155}, {"x": .4475, "y": .38}]}
    polygon = {"kind": "polygon", "points": [{"x": .51, "y": .2}, {"x": .8, "y": .4}, {"x": .62, "y": .76}]}
    try:
        created = client.post("/api/v1/admin/content/albumnesia", json={
            "album_title": title,
            "artist": "Test Artist",
            "alternative_answers": [f"{title} deluxe"],
            "release_year": 1999,
            "recognizable_track": "The Recognisable Single",
            "artist_initials": "TA",
            "difficulty": 5,
            "is_active": True,
            "enabled_distortions": ALL_DISTORTIONS,
            "text_mask_regions": [rectangle],
            "subject_mask_regions": [polygon],
            "staged_upload_id": upload["stage_id"],
        })
        assert created.status_code == 201, created.text
        item = created.json()
        content_id = item["id"]
        assert item["enabled_distortions"] == ALL_DISTORTIONS
        assert item["text_mask_regions"] == [rectangle]
        assert item["subject_mask_regions"] == [polygon]
        assert "crop_focus_x" not in item
        assert hashlib.sha256(client.get(item["image_url"]).content).hexdigest() == staged_digest

        new_rectangle = {"kind": "rectangle", "points": [{"x": .02, "y": .03}, {"x": .2, "y": .22}]}
        updated = client.patch(f"/api/v1/admin/content/{content_id}/albumnesia", json={
            "text_mask_regions": [new_rectangle],
            "subject_mask_regions": [polygon],
            "enabled_distortions": ALL_DISTORTIONS,
        })
        assert updated.status_code == 200, updated.text
        restored = client.get(f"/api/v1/admin/content/{content_id}").json()
        assert restored["text_mask_regions"] == [new_rectangle]
        assert restored["subject_mask_regions"] == [polygon]
        assert hashlib.sha256(client.get(restored["image_url"]).content).hexdigest() == staged_digest
    finally:
        delete_if_present(client, content_id)


def test_image_replacement_is_atomic_and_removes_unreferenced_old_file(content_client) -> None:
    client, storage = content_client
    content_id = None
    created = client.post("/api/v1/admin/content/badly-explained", json={
        "title": unique_answer("Replace image"), "clues": ["a", "b", "c", "d"],
        "alternative_answers": [], "difficulty": 2, "is_active": False,
        "staged_upload_id": stage(client)["stage_id"],
    })
    assert created.status_code == 201, created.text
    content_id = created.json()["id"]
    try:
        with SessionLocal() as session:
            old_key = session.get(ContentEntry, uuid.UUID(content_id)).image_key
        replacement = stage(client, "#d4a62a")
        response = client.post(f"/api/v1/admin/content/{content_id}/image", json={
            "staged_upload_id": replacement["stage_id"],
        })
        assert response.status_code == 200, response.text
        with SessionLocal() as session:
            new_key = session.get(ContentEntry, uuid.UUID(content_id)).image_key
        assert new_key != old_key
        assert not storage.exists(old_key)
        assert storage.exists(new_key)
    finally:
        delete_if_present(client, content_id)


def test_content_admin_auth_disabled_mode_and_ui_contract(content_client) -> None:
    client, _ = content_client
    unauthorized = TestClient(client.app)
    upload_response = unauthorized.post(
        "/api/v1/admin/uploads",
        files={"image": ("cover.png", image_bytes(), "image/png")},
    )
    assert upload_response.status_code == 401

    disabled = TestClient(create_app(Settings(DATABASE_URL=settings.database_url, ADMIN_ENABLED=False)))
    assert disabled.get("/admin/content").status_code == 404
    assert disabled.get("/api/v1/admin/content").status_code == 404

    page = client.get("/admin/content")
    assert page.status_code == 200
    source = page.text
    for label in ("Iconic Movies", "Badly Explained", "Guess Assemble", "Albumnesia"):
        assert label in source
    for technique in (
        "Pixel Hangover", "Sleeve Shredder", "Channel Damage", "Identity Crisis", "Outline Only",
    ):
        assert technique in source
    for obsolete in ("Palette Panic", "Extreme Close-Up", "Missing Persons", "Cover Scramble", "Mirror Dimension", "Minimal Evidence"):
        assert obsolete not in source
    for feature in ("upload-progress", "region-canvas", "subject-rectangle", "beforeunload", "Duplicate", "Preview", "Delete"):
        assert feature in source


def test_album_activation_and_normalized_coordinate_validation(content_client) -> None:
    client, storage = content_client
    invalid_coordinate = client.post("/api/v1/admin/content/albumnesia", json={
        "album_title": unique_answer("Bad coordinate"), "artist": "Artist",
        "recognizable_track": "Track", "artist_initials": "A", "difficulty": 3,
        "is_active": False, "enabled_distortions": ALL_DISTORTIONS,
        "text_mask_regions": [{"kind": "rectangle", "points": [{"x": 0, "y": 0}, {"x": 1.01, "y": 1}]}],
        "subject_mask_regions": [], "staged_upload_id": stage(client)["stage_id"],
    })
    assert invalid_coordinate.status_code == 422

    no_techniques = client.post("/api/v1/admin/content/albumnesia", json={
        "album_title": unique_answer("No techniques"), "artist": "Artist",
        "recognizable_track": "Track", "artist_initials": "A", "difficulty": 3,
        "is_active": True, "enabled_distortions": [], "text_mask_regions": [],
        "subject_mask_regions": [], "staged_upload_id": stage(client, "#445566")["stage_id"],
    })
    assert no_techniques.status_code == 422

    identity_without_subject = client.post("/api/v1/admin/content/albumnesia", json={
        "album_title": unique_answer("No subject"), "artist": "Artist",
        "recognizable_track": "Track", "artist_initials": "A", "difficulty": 3,
        "is_active": True, "enabled_distortions": ["identity_crisis"],
        "text_mask_regions": [], "subject_mask_regions": [],
        "staged_upload_id": stage(client, "#775544")["stage_id"],
    })
    assert identity_without_subject.status_code == 422
    for path in storage.staging_root.glob("*.webp"):
        path.unlink()


def test_cover_editor_drawing_and_seed_contract(content_client) -> None:
    source = content_client[0].get("/admin/content").text
    for contract in (
        "normalizedPoint(event)", "setPointerCapture", "pointerMove(event)",
        "ondblclick", "finishPolygon", "event.key==='Escape'", "Clear all regions",
        "Delete selected region", "window.addEventListener('resize'", "Regenerate variation",
        "crypto.getRandomValues", "drawPixelHangover", "drawSleeveShredder",
        "drawChannelDamage", "drawIdentityCrisis", "drawOutlineOnly", "obscureText",
    ):
        assert contract in source


def test_content_workflow_does_not_change_iconic_catalogue(content_client) -> None:
    client, _ = content_client
    with SessionLocal() as session:
        movie_count = session.scalar(select(func.count()).select_from(Movie))
    assert movie_count == 16
    assert any(movie["title"] == "Ant-Man" for movie in client.get("/api/v1/movies").json())
    assert client.get("/admin/puzzles").status_code == 200
