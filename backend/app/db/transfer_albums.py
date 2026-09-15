"""Insert-only content transfer. TARGET_DATABASE_URL must be supplied privately."""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, joinedload

from backend.app.models.entities import AlbumnesiaContent, BadlyExplainedContent, ContentEntry

CONTENT_FIELDS = (
    "id", "category", "primary_answer", "alternative_answers", "image_key",
    "difficulty", "is_active", "created_at", "updated_at",
)
ALBUM_FIELDS = (
    "artist", "release_year", "recognizable_track", "artist_initials",
    "enabled_distortions", "text_mask_regions", "subject_mask_regions",
)


def database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def check_image(root: Path, key: str) -> None:
    relative = PurePosixPath(key)
    resolved_root = root.resolve()
    candidate = (resolved_root / key).resolve()
    if (relative.is_absolute() or ".." in relative.parts or "\\" in key
            or not candidate.is_relative_to(resolved_root)
            or candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
            or not candidate.is_file()):
        raise ValueError(f"Missing or unsafe album image: {key}")


def transfer(source: Session, target: Session, asset_root: Path, category: str = "albumnesia") -> tuple[int, int]:
    """Stage inserts; caller owns commit/rollback. Never update existing content."""
    if category not in {"albumnesia", "badly_explained"}:
        raise ValueError("Unsupported transfer category")
    relation = "albumnesia" if category == "albumnesia" else "badly_explained"
    fields = ALBUM_FIELDS if category == "albumnesia" else ("clues",)
    model = AlbumnesiaContent if category == "albumnesia" else BadlyExplainedContent
    albums = list(source.scalars(select(ContentEntry).where(
        ContentEntry.category == category
    ).options(joinedload(getattr(ContentEntry, relation))).order_by(ContentEntry.id)))
    inserted = skipped = 0
    for entry in albums:
        metadata = getattr(entry, relation)
        if entry.category != category or metadata is None:
            raise ValueError(f"Content metadata missing or category mismatched for {entry.id}")
        check_image(asset_root, entry.image_key)
        existing = target.get(ContentEntry, entry.id)
        if existing:
            existing_metadata = getattr(existing, relation)
            if (existing_metadata is None
                    or any(getattr(existing, field) != getattr(entry, field) for field in CONTENT_FIELDS)
                    or any(getattr(existing_metadata, field) != getattr(metadata, field) for field in fields)):
                raise ValueError(f"Existing content differs for {entry.id}; refusing overwrite")
            skipped += 1
            continue
        conflict = target.scalar(select(ContentEntry.id).where(
            (ContentEntry.image_key == entry.image_key)
            | ((ContentEntry.category == category)
               & (ContentEntry.normalized_answer == entry.normalized_answer))
        ))
        if conflict:
            raise ValueError(f"Album conflicts with existing content {conflict}; refusing import")
        copied = ContentEntry(**{field: getattr(entry, field) for field in CONTENT_FIELDS})
        setattr(copied, relation, model(**{
            field: getattr(metadata, field) for field in fields
        }))
        target.add(copied)
        target.flush()
        inserted += 1
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit after all checks pass")
    parser.add_argument("--category", choices=("albumnesia", "badly_explained"), default="albumnesia")
    args = parser.parse_args()
    source_url = database_url(os.environ["DATABASE_URL"])
    target_url = database_url(os.environ["TARGET_DATABASE_URL"])
    if source_url == target_url:
        raise SystemExit("Source and target must be different databases")
    source_engine = create_engine(source_url, connect_args={"connect_timeout": 15})
    target_engine = create_engine(target_url, connect_args={"connect_timeout": 15})
    try:
        with Session(source_engine) as source, Session(target_engine) as target:
            source.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
            inserted, skipped = transfer(source, target, Path(os.environ.get("ASSET_ROOT", "assets/scenes")), args.category)
            if args.apply:
                target.commit()
            else:
                target.rollback()
            label = "albums" if args.category == "albumnesia" else "Badly Explained entries"
            print(f"{'Imported' if args.apply else 'Dry run (rolled back)'}: {inserted} {label}; {skipped} identical {label} skipped")
    except Exception:
        # Connection exceptions can contain credentials; do not print them.
        raise SystemExit("Transfer failed and uncommitted changes rolled back. Check connectivity, migrations, images, or content conflicts. Database credentials were not printed.") from None
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    main()
