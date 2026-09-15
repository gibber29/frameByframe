"""Add shared content management and category-specific records.

Revision ID: 20260913_0008
Revises: 20260913_0007
Create Date: 2026-09-13
"""

from alembic import op

revision = "20260913_0008"
down_revision = "20260913_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE framebyframe.content_entries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            category varchar(40) NOT NULL CONSTRAINT content_category_valid
                CHECK (category IN ('badly_explained', 'albumnesia', 'guess_assemble')),
            primary_answer text NOT NULL CONSTRAINT content_primary_answer_not_blank
                CHECK (btrim(primary_answer) <> ''),
            normalized_answer text GENERATED ALWAYS AS (framebyframe.normalize_title(primary_answer)) STORED,
            alternative_answers jsonb NOT NULL DEFAULT '[]'::jsonb
                CONSTRAINT content_alternatives_array CHECK (jsonb_typeof(alternative_answers) = 'array'),
            image_key text NOT NULL UNIQUE,
            difficulty smallint NOT NULL DEFAULT 3 CONSTRAINT content_difficulty_range CHECK (difficulty BETWEEN 1 AND 5),
            is_active boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX content_entries_filters_idx ON framebyframe.content_entries(category, is_active, difficulty);
        CREATE INDEX content_entries_answer_idx ON framebyframe.content_entries(normalized_answer);

        CREATE TABLE framebyframe.badly_explained_content (
            content_id uuid PRIMARY KEY REFERENCES framebyframe.content_entries(id) ON DELETE CASCADE,
            clues jsonb NOT NULL CONSTRAINT exactly_four_clues
                CHECK (jsonb_typeof(clues) = 'array' AND jsonb_array_length(clues) = 4)
        );

        CREATE TABLE framebyframe.albumnesia_content (
            content_id uuid PRIMARY KEY REFERENCES framebyframe.content_entries(id) ON DELETE CASCADE,
            artist text NOT NULL,
            release_year smallint CONSTRAINT album_release_year_range
                CHECK (release_year IS NULL OR release_year BETWEEN 1888 AND 2200),
            recognizable_track text NOT NULL,
            artist_initials varchar(30) NOT NULL,
            enabled_distortions jsonb NOT NULL,
            crop_focus_x numeric(5,2) NOT NULL DEFAULT 50.00 CONSTRAINT album_crop_x_range CHECK (crop_focus_x BETWEEN 0 AND 100),
            crop_focus_y numeric(5,2) NOT NULL DEFAULT 50.00 CONSTRAINT album_crop_y_range CHECK (crop_focus_y BETWEEN 0 AND 100),
            text_mask_regions jsonb NOT NULL DEFAULT '[]'::jsonb,
            subject_mask_regions jsonb NOT NULL DEFAULT '[]'::jsonb,
            CONSTRAINT album_distortions_array CHECK (jsonb_typeof(enabled_distortions) = 'array'),
            CONSTRAINT album_text_masks_array CHECK (jsonb_typeof(text_mask_regions) = 'array'),
            CONSTRAINT album_subject_masks_array CHECK (jsonb_typeof(subject_mask_regions) = 'array')
        );
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE framebyframe.albumnesia_content;
        DROP TABLE framebyframe.badly_explained_content;
        DROP TABLE framebyframe.content_entries;
    """)
