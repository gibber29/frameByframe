from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

from PIL import Image, ImageOps, UnidentifiedImageError

SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
SUPPORTED_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})


class InvalidAssetPathError(ValueError):
    pass


class InvalidImageError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


class AssetNotFoundError(FileNotFoundError):
    pass


@dataclass(frozen=True)
class LocalAsset:
    asset_id: str
    image_key: str
    movie_directory: str


@dataclass(frozen=True)
class StagedAsset:
    stage_id: str
    sanitized_filename: str
    width: int
    height: int
    size_bytes: int


class AssetStorage(Protocol):
    def save_staged(self, source: BinaryIO, filename: str, max_bytes: int, quality: int) -> StagedAsset: ...
    def finalize(self, stage_id: str, movie_slug: str) -> str: ...
    def open(self, image_key: str) -> BinaryIO: ...
    def exists(self, image_key: str) -> bool: ...
    def delete(self, image_key: str) -> None: ...
    def copy(self, image_key: str, storage_directory: str) -> str: ...
    def delete_staged(self, stage_id: str) -> None: ...
    def public_or_private_url(self, image_key: str) -> str | None: ...


class LocalFilesystemStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.staging_root = self.root / ".staging"

    @staticmethod
    def asset_id(image_key: str) -> str:
        return hashlib.sha256(image_key.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        leaf = PurePosixPath((filename or "upload").replace("\\", "/")).name
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(leaf).stem).strip(".-_") or "upload"
        return f"{stem[:80].lower()}.webp"

    @staticmethod
    def _stage_uuid(stage_id: str) -> uuid.UUID:
        try:
            return uuid.UUID(stage_id)
        except (ValueError, AttributeError) as exc:
            raise InvalidAssetPathError("Invalid staged upload identifier") from exc

    def _stage_path(self, stage_id: str) -> Path:
        return self.staging_root / f"{self._stage_uuid(stage_id).hex}.webp"

    def save_staged(self, source: BinaryIO, filename: str, max_bytes: int, quality: int = 86) -> StagedAsset:
        data = source.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise UploadTooLargeError(f"Upload exceeds the {max_bytes}-byte limit")
        if not data:
            raise InvalidImageError("Uploaded image is empty")
        try:
            with Image.open(BytesIO(data)) as original:
                if original.format not in SUPPORTED_IMAGE_FORMATS:
                    raise InvalidImageError("Only WebP, PNG, and JPEG images are supported")
                original.verify()
            with Image.open(BytesIO(data)) as original:
                image = ImageOps.exif_transpose(original)
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "transparency" in image.info else "RGB")
                width, height = image.size
                if width < 1 or height < 1:
                    raise InvalidImageError("Image dimensions are invalid")
                stage_id = str(uuid.uuid4())
                self.staging_root.mkdir(parents=True, exist_ok=True)
                path = self._stage_path(stage_id)
                image.save(path, format="WEBP", quality=max(1, min(100, quality)), method=6)
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise InvalidImageError("Uploaded file is not a valid supported image") from exc
        return StagedAsset(stage_id, self.sanitize_filename(filename), width, height, path.stat().st_size)

    def staged_path(self, stage_id: str) -> Path:
        path = self._stage_path(stage_id)
        if not path.is_file():
            raise AssetNotFoundError("Staged upload does not exist")
        return path

    def finalize(self, stage_id: str, movie_slug: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", movie_slug):
            raise InvalidAssetPathError("Invalid movie slug")
        source = self.staged_path(stage_id)
        image_key = f"{movie_slug}/{uuid.uuid4().hex}.webp"
        destination = self.root / Path(*PurePosixPath(image_key).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            source.replace(destination)
        except OSError:
            shutil.move(str(source), str(destination))
        return image_key

    def copy(self, image_key: str, storage_directory: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", storage_directory):
            raise InvalidAssetPathError("Invalid storage directory")
        source = self.resolve(image_key)
        copied_key = f"{storage_directory}/{uuid.uuid4().hex}.webp"
        destination = self.root / Path(*PurePosixPath(copied_key).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return copied_key

    def delete_staged(self, stage_id: str) -> None:
        self._stage_path(stage_id).unlink(missing_ok=True)

    def discover(self) -> list[LocalAsset]:
        if not self.root.is_dir():
            return []
        assets: list[LocalAsset] = []
        for path in sorted(self.root.rglob("*")):
            if self.staging_root in path.parents:
                continue
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                relative = path.relative_to(self.root).as_posix()
                parts = PurePosixPath(relative).parts
                if len(parts) == 2:
                    assets.append(LocalAsset(self.asset_id(relative), relative, parts[0]))
        return assets

    def resolve(self, image_key: str, movie_directory: str | None = None) -> Path:
        if not image_key or "\\" in image_key:
            raise InvalidAssetPathError("Invalid image key")
        relative = PurePosixPath(image_key)
        if relative.is_absolute() or len(relative.parts) != 2 or any(part in {"", ".", ".."} for part in relative.parts):
            raise InvalidAssetPathError("Invalid image key")
        if relative.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise InvalidAssetPathError("Unsupported image type")
        if movie_directory is not None and relative.parts[0] != movie_directory:
            raise InvalidAssetPathError("Image does not belong to the selected movie")
        candidate = (self.root / Path(*relative.parts)).resolve()
        if not candidate.is_relative_to(self.root):
            raise InvalidAssetPathError("Invalid image key")
        if not candidate.is_file():
            raise AssetNotFoundError("Image file does not exist")
        return candidate

    def open(self, image_key: str) -> BinaryIO:
        return self.resolve(image_key).open("rb")

    def exists(self, image_key: str) -> bool:
        try:
            self.resolve(image_key)
            return True
        except (InvalidAssetPathError, AssetNotFoundError):
            return False

    def delete(self, image_key: str) -> None:
        try:
            path = self.resolve(image_key)
        except AssetNotFoundError:
            return
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass

    def resolve_asset_id(self, asset_id: str) -> tuple[LocalAsset, Path]:
        for asset in self.discover():
            if asset.asset_id == asset_id:
                return asset, self.resolve(asset.image_key)
        raise AssetNotFoundError("Asset does not exist")

    @staticmethod
    def public_or_private_url(image_key: str) -> None:
        return None

    @staticmethod
    def media_type(path: Path) -> str:
        return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[path.suffix.lower()]


LocalAssetStorage = LocalFilesystemStorage
