from pathlib import Path
from io import BytesIO

import pytest
from PIL import Image

from backend.app.storage.assets import (
    InvalidAssetPathError, InvalidImageError, LocalAssetStorage, UploadTooLargeError,
)


def test_asset_discovery_filters_extensions_and_requires_movie_directory(tmp_path: Path) -> None:
    movie_dir = tmp_path / "sample-movie"
    movie_dir.mkdir()
    (movie_dir / "scene.webp").write_bytes(b"image")
    (movie_dir / "scene.PNG").write_bytes(b"image")
    (movie_dir / "notes.txt").write_text("not an image")
    (tmp_path / "root.jpg").write_bytes(b"not in a movie directory")

    assets = LocalAssetStorage(tmp_path).discover()

    assert {asset.image_key for asset in assets} == {"sample-movie/scene.webp", "sample-movie/scene.PNG"}
    assert all(len(asset.asset_id) == 24 for asset in assets)


@pytest.mark.parametrize(
    "image_key",
    ["../secret.png", "sample-movie/../../secret.png", "/etc/passwd", "sample-movie\\scene.png", "sample-movie/file.gif"],
)
def test_path_traversal_and_unsupported_files_are_rejected(tmp_path: Path, image_key: str) -> None:
    with pytest.raises(InvalidAssetPathError):
        LocalAssetStorage(tmp_path).resolve(image_key)


def test_asset_must_belong_to_selected_movie_directory(tmp_path: Path) -> None:
    movie_dir = tmp_path / "sample-movie"
    movie_dir.mkdir()
    (movie_dir / "scene.jpg").write_bytes(b"image")

    with pytest.raises(InvalidAssetPathError, match="selected movie"):
        LocalAssetStorage(tmp_path).resolve("sample-movie/scene.jpg", "different-movie")


def image_bytes(format_name: str, size: tuple[int, int] = (31, 19)) -> BytesIO:
    output = BytesIO()
    Image.new("RGB", size, "#8a2432").save(output, format=format_name)
    output.seek(0)
    return output


@pytest.mark.parametrize(("format_name", "filename"), [("PNG", "scene.png"), ("JPEG", "scene.jpeg")])
def test_png_and_jpeg_are_staged_as_webp_without_upscaling(
    tmp_path: Path, format_name: str, filename: str
) -> None:
    storage = LocalAssetStorage(tmp_path)
    staged = storage.save_staged(image_bytes(format_name), filename, 100_000, 85)

    path = storage.staged_path(staged.stage_id)
    with Image.open(path) as converted:
        assert converted.format == "WEBP"
        assert converted.size == (31, 19)
    assert staged.sanitized_filename == "scene.webp"


def test_actual_content_size_and_filename_are_validated(tmp_path: Path) -> None:
    storage = LocalAssetStorage(tmp_path)
    with pytest.raises(InvalidImageError):
        storage.save_staged(BytesIO(b"not a png"), "looks-real.png", 1000, 85)
    with pytest.raises(InvalidImageError):
        storage.save_staged(image_bytes("GIF"), "animation.gif", 100_000, 85)
    with pytest.raises(UploadTooLargeError):
        storage.save_staged(image_bytes("PNG"), "large.png", 10, 85)
    assert storage.sanitize_filename("../../My dangerous scene.PNG") == "my-dangerous-scene.webp"


def test_staging_identifiers_and_generated_movie_slugs_reject_traversal(tmp_path: Path) -> None:
    storage = LocalAssetStorage(tmp_path)
    staged = storage.save_staged(image_bytes("PNG"), "scene.png", 100_000, 85)
    with pytest.raises(InvalidAssetPathError):
        storage.finalize(staged.stage_id, "../outside")
    with pytest.raises(InvalidAssetPathError):
        storage.staged_path("../../outside")


def test_exif_orientation_is_applied_before_webp_conversion(tmp_path: Path) -> None:
    source = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (20, 10), "navy").save(source, format="JPEG", exif=exif)
    source.seek(0)
    storage = LocalAssetStorage(tmp_path)
    staged = storage.save_staged(source, "rotated.jpg", 100_000, 85)
    with Image.open(storage.staged_path(staged.stage_id)) as converted:
        assert converted.size == (10, 20)
