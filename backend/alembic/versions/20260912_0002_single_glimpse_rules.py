"""Configure the single-glimpse reveal sequence and remove replay penalties.

Revision ID: 20260912_0002
Revises: 20260912_0001
Create Date: 2026-09-12
"""

from alembic import op

revision = "20260912_0002"
down_revision = "20260912_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE framebyframe.reveal_stages AS stage
        SET radius_percent = values.radius_percent,
            duration_ms = values.duration_ms,
            show_full_image = values.show_full_image
        FROM framebyframe.reveal_profiles AS profile,
             (VALUES
                (1::smallint, 14.00::numeric, 100, false),
                (2::smallint, 22.00::numeric, 500, false),
                (3::smallint, 32.00::numeric, 1000, false),
                (4::smallint, 45.00::numeric, 2000, false),
                (5::smallint, NULL::numeric, 5000, true)
             ) AS values(round_number, radius_percent, duration_ms, show_full_image)
        WHERE stage.profile_id = profile.id
          AND profile.name = 'Default five-turn reveal'
          AND stage.round_number = values.round_number
        """
    )
    op.execute("ALTER TABLE framebyframe.rule_sets ALTER COLUMN replay_penalty SET DEFAULT 0")
    op.execute("UPDATE framebyframe.rule_sets SET replay_penalty = 0 WHERE name = 'Prototype v1'")


def downgrade() -> None:
    op.execute(
        """
        UPDATE framebyframe.reveal_stages AS stage
        SET radius_percent = values.radius_percent,
            duration_ms = values.duration_ms,
            show_full_image = values.show_full_image
        FROM framebyframe.reveal_profiles AS profile,
             (VALUES
                (1::smallint, 5.00::numeric, 200, false),
                (2::smallint, 10.00::numeric, 400, false),
                (3::smallint, 18.00::numeric, 600, false),
                (4::smallint, 30.00::numeric, 800, false),
                (5::smallint, NULL::numeric, 1200, true)
             ) AS values(round_number, radius_percent, duration_ms, show_full_image)
        WHERE stage.profile_id = profile.id
          AND profile.name = 'Default five-turn reveal'
          AND stage.round_number = values.round_number
        """
    )
    op.execute("UPDATE framebyframe.rule_sets SET replay_penalty = 30 WHERE name = 'Prototype v1'")
    op.execute("ALTER TABLE framebyframe.rule_sets ALTER COLUMN replay_penalty SET DEFAULT 30")
