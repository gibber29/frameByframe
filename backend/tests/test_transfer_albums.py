import uuid
import pytest
from sqlalchemy.orm import Session

from backend.app.db.session import engine
from backend.app.db.transfer_albums import check_image, database_url, transfer
from backend.app.models.entities import AlbumnesiaContent, BadlyExplainedContent, ContentEntry


def test_url_conversion():
    assert database_url("postgresql://host/db") == "postgresql+psycopg://host/db"
    assert database_url("postgres://host/db") == "postgresql+psycopg://host/db"


def test_asset_validation(tmp_path):
    (tmp_path / "cover.webp").write_bytes(b"image")
    check_image(tmp_path, "cover.webp")
    for key in ("../cover.webp", "/cover.webp", "missing.jpg", "cover.txt", "..\\cover.webp"):
        with pytest.raises(ValueError):
            check_image(tmp_path, key)


@pytest.mark.parametrize("category", ["albumnesia", "badly_explained"])
def test_insert_and_idempotency(tmp_path, category):
    entry = ContentEntry(
        id=uuid.uuid4(), category=category, primary_answer=f"Transfer {uuid.uuid4()}",
        alternative_answers=["Alternative"], image_key=f"{uuid.uuid4()}.webp",
        difficulty=3, is_active=False,
    )
    entry.albumnesia = AlbumnesiaContent(
        artist="Artist", release_year=2000, recognizable_track="Track", artist_initials="A",
        enabled_distortions=["outline_only"], text_mask_regions=[], subject_mask_regions=[],
    )
    if category == "badly_explained":
        entry.albumnesia = None
        entry.badly_explained = BadlyExplainedContent(clues=["One", "Two", "Three", "Four"])
    (tmp_path / entry.image_key).write_bytes(b"image")
    # A source facade keeps this test independent of existing authored albums.
    class Source:
        def scalars(self, statement):
            return [entry]
    with Session(engine) as target:
        # Defaults are populated by PostgreSQL on the first insert.
        assert transfer(Source(), target, tmp_path, category) == (1, 0)
        entry.created_at = target.get(ContentEntry, entry.id).created_at
        entry.updated_at = target.get(ContentEntry, entry.id).updated_at
        assert transfer(Source(), target, tmp_path, category) == (0, 1)
        if category == "badly_explained":
            assert target.get(ContentEntry, entry.id).badly_explained.clues == ["One", "Two", "Three", "Four"]
        entry.primary_answer = "Changed"
        with pytest.raises(ValueError, match="refusing overwrite"):
            transfer(Source(), target, tmp_path, category)
        target.rollback()
