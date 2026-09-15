"""Replace Albumnesia distortions and normalize mask coordinates.

Revision ID: 20260914_0009
Revises: 20260913_0008
Create Date: 2026-09-14
"""

from alembic import op

revision = "20260914_0009"
down_revision = "20260913_0008"
branch_labels = None
depends_on = None

FINAL_DISTORTIONS = """[
    "pixel_hangover", "sleeve_shredder", "channel_damage",
    "identity_crisis", "outline_only"
]"""
FINAL_WITHOUT_IDENTITY = """[
    "pixel_hangover", "sleeve_shredder", "channel_damage", "outline_only"
]"""
LEGACY_DISTORTIONS = """[
    "palette_panic", "extreme_close_up", "pixel_hangover", "missing_persons",
    "cover_scramble", "mirror_dimension", "minimal_evidence"
]"""


def convert_region_coordinates(column: str, divisor: int) -> None:
    op.execute(f"""
        UPDATE framebyframe.albumnesia_content AS album
        SET {column} = COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'kind', region->'kind',
                    'points', COALESCE((
                        SELECT jsonb_agg(jsonb_build_object(
                            'x', round((point->>'x')::numeric / {divisor}, 6),
                            'y', round((point->>'y')::numeric / {divisor}, 6)
                        ))
                        FROM jsonb_array_elements(region->'points') AS point
                    ), '[]'::jsonb)
                )
            )
            FROM jsonb_array_elements(album.{column}) AS region
        ), '[]'::jsonb)
    """)


def upgrade() -> None:
    # Existing masks were percentages. The editor and API now use normalized
    # fractions so the same regions align at every rendered size.
    convert_region_coordinates("text_mask_regions", 100)
    convert_region_coordinates("subject_mask_regions", 100)

    op.execute(f"""
        UPDATE framebyframe.albumnesia_content AS album
        SET enabled_distortions = CASE
            WHEN entry.is_active AND jsonb_array_length(album.subject_mask_regions) = 0
                THEN '{FINAL_WITHOUT_IDENTITY}'::jsonb
            ELSE '{FINAL_DISTORTIONS}'::jsonb
        END
        FROM framebyframe.content_entries AS entry
        WHERE entry.id = album.content_id
    """)

    op.execute("""
        ALTER TABLE framebyframe.albumnesia_content
            DROP COLUMN crop_focus_x,
            DROP COLUMN crop_focus_y,
            ADD CONSTRAINT album_distortions_allowed CHECK (
                enabled_distortions <@ '[
                    "pixel_hangover", "sleeve_shredder", "channel_damage",
                    "identity_crisis", "outline_only"
                ]'::jsonb
            ),
            ADD CONSTRAINT album_text_mask_coordinates_normalized CHECK (
                NOT jsonb_path_exists(
                    text_mask_regions,
                    '$[*].points[*] ? (@.x < 0 || @.x > 1 || @.y < 0 || @.y > 1)'
                )
            ),
            ADD CONSTRAINT album_subject_mask_coordinates_normalized CHECK (
                NOT jsonb_path_exists(
                    subject_mask_regions,
                    '$[*].points[*] ? (@.x < 0 || @.x > 1 || @.y < 0 || @.y > 1)'
                )
            )
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE framebyframe.albumnesia_content
            DROP CONSTRAINT album_subject_mask_coordinates_normalized,
            DROP CONSTRAINT album_text_mask_coordinates_normalized,
            DROP CONSTRAINT album_distortions_allowed,
            ADD COLUMN crop_focus_x numeric(5,2) NOT NULL DEFAULT 50.00
                CONSTRAINT album_crop_x_range CHECK (crop_focus_x BETWEEN 0 AND 100),
            ADD COLUMN crop_focus_y numeric(5,2) NOT NULL DEFAULT 50.00
                CONSTRAINT album_crop_y_range CHECK (crop_focus_y BETWEEN 0 AND 100)
    """)
    convert_region_coordinates("text_mask_regions", 0.01)
    convert_region_coordinates("subject_mask_regions", 0.01)
    op.execute(f"""
        UPDATE framebyframe.albumnesia_content
        SET enabled_distortions = '{LEGACY_DISTORTIONS}'::jsonb
    """)
