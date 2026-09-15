import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete

from backend.app.api.dependencies import get_asset_storage
from backend.app.core.config import Settings, settings
from backend.app.db.session import SessionLocal
from backend.app.main import create_app
from backend.app.models.entities import Puzzle
from backend.app.storage import LocalFilesystemStorage


client: TestClient


@pytest.fixture(scope="module", autouse=True)
def isolated_unused_assets(tmp_path_factory: pytest.TempPathFactory):
    global client
    root = tmp_path_factory.mktemp("admin-assets")
    original_storage = LocalFilesystemStorage(settings.asset_root)
    for asset in original_storage.discover():
        destination = root / Path(*Path(asset.image_key).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(original_storage.resolve(asset.image_key).read_bytes())
    for index, directory in enumerate(("ant-man", "avengers-endgame", "avengers-infinity-war", "black-panther")):
        destination = root / directory / f"test-{index}.webp"
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (12, 12), f"#{index + 2}04488").save(destination, "WEBP")
    storage = LocalFilesystemStorage(root)
    app = create_app()
    app.dependency_overrides[get_asset_storage] = lambda: storage
    with TestClient(app, headers={"X-Admin-Token": settings.admin_token}) as test_client:
        client = test_client
        yield


def assets():
    response = client.get("/api/v1/admin/assets")
    assert response.status_code == 200
    return response.json()


def puzzle_payload(asset_index: int = 0) -> dict:
    catalog = assets()
    used_keys = {
        puzzle["image_key"] for puzzle in client.get("/api/v1/admin/puzzles").json()
    }
    available_assets = [asset for asset in catalog["assets"] if asset["image_key"] not in used_keys]
    asset = available_assets[asset_index]
    return {
        "movie_id": asset["movie_id"],
        "image_key": asset["image_key"],
        "stage_regions": [
            {"round_number": round_number, "reveal_x": 20 + round_number, "reveal_y": 70 - round_number}
            for round_number in range(1, 5)
        ],
        "cryptic_hint": asset["suggested_hint"],
        "difficulty": 3,
        "reveal_profile_id": catalog["reveal_profiles"][0]["id"],
        "status": "draft",
    }


@contextmanager
def created_puzzle(asset_index: int):
    response = client.post("/api/v1/admin/puzzles", json=puzzle_payload(asset_index))
    assert response.status_code == 201, response.text
    puzzle = response.json()
    try:
        yield puzzle
    finally:
        with SessionLocal.begin() as session:
            session.execute(delete(Puzzle).where(Puzzle.id == uuid.UUID(puzzle["id"])))


def test_assets_are_discovered_and_preview_urls_do_not_contain_titles() -> None:
    catalog = assets()

    assert len(catalog["assets"]) >= 16
    assert len(catalog["reveal_profiles"][0]["stages"]) == 5
    assert [stage["duration_ms"] for stage in catalog["reveal_profiles"][0]["stages"]] == [200, 300, 300, 400, 500]
    first = catalog["assets"][0]
    assert first["image_key"] not in first["image_url"]
    assert first["movie_title"].lower().replace(" ", "-") not in first["image_url"]


def test_ant_man_image_is_associated_with_the_canonical_movie() -> None:
    ant_man_assets = [
        asset for asset in assets()["assets"] if asset["movie_title"] == "Ant-Man"
    ]

    assert any(asset["image_key"] == "ant-man/ant-man.webp" for asset in ant_man_assets)


def test_coordinate_validation() -> None:
    payload = puzzle_payload()
    payload["stage_regions"][0]["reveal_x"] = 100.01

    response = client.post("/api/v1/admin/puzzles", json=payload)

    assert response.status_code == 422


def test_backend_rejects_image_from_a_different_movie_directory() -> None:
    catalog = assets()
    ant_man = next(asset for asset in catalog["assets"] if asset["movie_title"] == "Ant-Man")
    endgame = next(asset for asset in catalog["assets"] if asset["movie_title"] == "Avengers: Endgame")
    payload = puzzle_payload()
    payload["movie_id"] = ant_man["movie_id"]
    payload["image_key"] = endgame["image_key"]

    response = client.post("/api/v1/admin/puzzles", json=payload)

    assert response.status_code == 422
    assert "selected movie" in response.json()["detail"]


def test_draft_creation_and_detail() -> None:
    payload = puzzle_payload(0)
    payload["stage_regions"] = payload["stage_regions"][:1]
    response = client.post("/api/v1/admin/puzzles", json=payload)
    assert response.status_code == 201, response.text
    puzzle = response.json()
    try:
        assert puzzle["status"] == "draft"
        assert puzzle["stage_regions"] == [
            {"round_number": 1, "reveal_x": "21.00", "reveal_y": "69.00"}
        ]
        detail = client.get(f"/api/v1/admin/puzzles/{puzzle['id']}")
        assert detail.status_code == 200
        assert detail.json()["id"] == puzzle["id"]
    finally:
        with SessionLocal.begin() as session:
            session.execute(delete(Puzzle).where(Puzzle.id == uuid.UUID(puzzle["id"])))


def test_ready_state_requires_valid_fields_and_profile() -> None:
    with created_puzzle(1) as puzzle:
        invalid = client.patch(
            f"/api/v1/admin/puzzles/{puzzle['id']}",
            json={"status": "ready", "reveal_profile_id": str(uuid.uuid4())},
        )
        assert invalid.status_code == 422

        ready = client.patch(f"/api/v1/admin/puzzles/{puzzle['id']}", json={"status": "ready"})
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"


def test_ready_state_requires_all_four_stage_regions() -> None:
    payload = puzzle_payload(3)
    payload["stage_regions"] = payload["stage_regions"][:3]
    payload["status"] = "ready"

    response = client.post("/api/v1/admin/puzzles", json=payload)

    assert response.status_code == 422
    assert "rounds 1 through 4" in response.json()["detail"]


def test_puzzle_image_serving_uses_opaque_url() -> None:
    with created_puzzle(2) as puzzle:
        assert puzzle["image_key"] not in puzzle["image_url"]
        response = client.get(puzzle["image_url"])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/")
        assert response.content


def test_admin_routes_are_absent_when_disabled() -> None:
    disabled = Settings(
        DATABASE_URL=settings.database_url,
        ADMIN_ENABLED=False,
        ASSET_ROOT=settings.asset_root,
    )
    disabled_client = TestClient(create_app(disabled))

    assert disabled_client.get("/api/v1/admin/assets").status_code == 404
    assert disabled_client.get("/admin/puzzles").status_code == 404


def test_admin_preview_keeps_authoring_playback_and_uses_precise_timing() -> None:
    response = client.get("/admin/puzzles")

    assert response.status_code == 200
    assert "Play Actual Glimpse" in response.text
    assert "await decodeImage(image)" in response.text
    assert "performance.now()" in response.text
    assert "visibilitychange" in response.text
    assert "transition:none" in response.text
    assert "image.style.visibility = 'hidden'" in response.text


def test_admin_stage_selection_drives_persistent_main_preview() -> None:
    page = client.get("/admin/puzzles").text

    assert 'id="stage-selector"' in page
    assert 'id="reveal-mask"' in page
    assert "function selectStage(round)" in page
    assert "state.selectedStage=round" in page
    assert "state.stageRegions[state.selectedStage]" in page
    assert "updatePersistentPreview()" in page
    assert "stage.show_full_image" in page
    assert "Reveal regions configured: 0 / 4" in page
    assert "Copy previous stage position" in page


def test_admin_pointer_click_and_drag_update_coordinates() -> None:
    page = client.get("/admin/puzzles").text

    assert "onpointerdown" in page
    assert "onpointermove" in page
    assert "setPointerCapture" in page
    assert "function updateFromPointer(event)" in page
    assert "setCoordinates(" in page
    assert "Math.min(100,Math.max(0,Number(x)))" in page
    assert "stage_regions:Object.values(state.stageRegions)" in page


def test_admin_radius_uses_shorter_rendered_image_dimension() -> None:
    page = client.get("/admin/puzzles").text

    assert "function renderedRadius(radiusPercent,width,height)" in page
    assert "Math.min(width,height)*Number(radiusPercent)/100" in page
    assert "radius * 2" in page
    assert "circle(${radius}px" in page


def test_new_then_endgame_create_state_flow_contract() -> None:
    catalog = assets()
    endgame = next(asset for asset in catalog["assets"] if asset["movie_title"] == "Avengers: Endgame")
    page = client.get("/admin/puzzles").text

    assert endgame["image_key"] == "avengers-endgame/avengers_endgame.webp"
    assert endgame["suggested_hint"] == "America’s backside receives official recognition."
    assert "function reset()" in page
    assert "state.puzzleId=null" in page
    assert "state.stageRegions={}" in page
    assert "function applyMovieSelection(movieId)" in page
    assert "$('hint').value=assets[0]?.suggested_hint||''" in page
    assert "Creating puzzle for ${title}" in page
    assert "Changing the movie will discard unsaved puzzle changes" in page
