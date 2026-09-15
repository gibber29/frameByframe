"""Apply the final short reveal-stage timings.

Revision ID: 20260912_0003
Revises: 20260912_0002
Create Date: 2026-09-12
"""

from alembic import op

revision = "20260912_0003"
down_revision = "20260912_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE framebyframe.reveal_stages AS stage
        SET duration_ms = values.duration_ms
        FROM framebyframe.reveal_profiles AS profile,
             (VALUES
                (1::smallint, 200),
                (2::smallint, 200),
                (3::smallint, 300),
                (4::smallint, 300),
                (5::smallint, 400)
             ) AS values(round_number, duration_ms)
        WHERE stage.profile_id = profile.id
          AND profile.name = 'Default five-turn reveal'
          AND stage.round_number = values.round_number
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE framebyframe.reveal_stages AS stage
        SET duration_ms = values.duration_ms
        FROM framebyframe.reveal_profiles AS profile,
             (VALUES
                (1::smallint, 100),
                (2::smallint, 500),
                (3::smallint, 1000),
                (4::smallint, 2000),
                (5::smallint, 5000)
             ) AS values(round_number, duration_ms)
        WHERE stage.profile_id = profile.id
          AND profile.name = 'Default five-turn reveal'
          AND stage.round_number = values.round_number
        """
    )
