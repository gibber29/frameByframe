"""Refine Albumnesia completion, scoring scale, and room metadata.

Revision ID: 20260914_0011
Revises: 20260914_0010
Create Date: 2026-09-14
"""

from alembic import op

revision = "20260914_0011"
down_revision = "20260914_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE framebyframe.albumnesia_attempts
            DROP CONSTRAINT albumnesia_total_score_range,
            ADD COLUMN score_scale numeric(8,2);
        UPDATE framebyframe.albumnesia_attempts SET score_scale = 250.00;
        ALTER TABLE framebyframe.albumnesia_attempts
            ALTER COLUMN score_scale SET NOT NULL,
            ALTER COLUMN score_scale SET DEFAULT 50.00,
            ADD CONSTRAINT albumnesia_score_scale_allowed CHECK (score_scale IN (50.00, 250.00)),
            ADD CONSTRAINT albumnesia_total_score_range CHECK (total_score BETWEEN 0 AND score_scale);

        ALTER TABLE framebyframe.albumnesia_rooms
            ADD COLUMN host_display_name varchar(40),
            ADD COLUMN status varchar(16) NOT NULL DEFAULT 'open';
        UPDATE framebyframe.albumnesia_rooms AS room
        SET host_display_name = (
            SELECT display_name FROM framebyframe.albumnesia_participants
            WHERE room_id = room.id ORDER BY created_at LIMIT 1
        );
        UPDATE framebyframe.albumnesia_rooms SET host_display_name = 'Host' WHERE host_display_name IS NULL;
        ALTER TABLE framebyframe.albumnesia_rooms
            ALTER COLUMN host_display_name SET NOT NULL,
            ADD CONSTRAINT albumnesia_host_name_not_blank CHECK (btrim(host_display_name) <> ''),
            ADD CONSTRAINT albumnesia_room_status_allowed CHECK (status IN ('open', 'expired'));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE framebyframe.albumnesia_rooms
            DROP CONSTRAINT albumnesia_room_status_allowed,
            DROP CONSTRAINT albumnesia_host_name_not_blank,
            DROP COLUMN status,
            DROP COLUMN host_display_name;
        ALTER TABLE framebyframe.albumnesia_attempts
            DROP CONSTRAINT albumnesia_total_score_range,
            DROP CONSTRAINT albumnesia_score_scale_allowed,
            DROP COLUMN score_scale,
            ADD CONSTRAINT albumnesia_total_score_range CHECK (total_score BETWEEN 0 AND 250);
    """)
