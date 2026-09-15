"""Version daily Albumnesia sets for the one-album format.

Revision ID: 20260914_0012
Revises: 20260914_0011
Create Date: 2026-09-14
"""

from alembic import op

revision = "20260914_0012"
down_revision = "20260914_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE framebyframe.albumnesia_game_sets ADD COLUMN game_version smallint;
        UPDATE framebyframe.albumnesia_game_sets SET game_version = 1;
        ALTER TABLE framebyframe.albumnesia_game_sets
            ALTER COLUMN game_version SET NOT NULL,
            ALTER COLUMN game_version SET DEFAULT 2,
            ADD CONSTRAINT albumnesia_game_version_positive CHECK (game_version > 0);
        DROP INDEX framebyframe.albumnesia_daily_set_date_unique;
        CREATE UNIQUE INDEX albumnesia_daily_set_date_version_unique
            ON framebyframe.albumnesia_game_sets(game_date, game_version)
            WHERE kind = 'daily';

        ALTER TABLE framebyframe.albumnesia_attempts
            DROP CONSTRAINT albumnesia_score_scale_allowed,
            ADD CONSTRAINT albumnesia_score_scale_allowed CHECK (score_scale IN (10.00, 50.00, 250.00));
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM framebyframe.albumnesia_game_sets WHERE kind = 'daily' AND game_version > 1;
        DROP INDEX framebyframe.albumnesia_daily_set_date_version_unique;
        CREATE UNIQUE INDEX albumnesia_daily_set_date_unique
            ON framebyframe.albumnesia_game_sets(game_date) WHERE kind = 'daily';
        ALTER TABLE framebyframe.albumnesia_game_sets DROP CONSTRAINT albumnesia_game_version_positive;
        ALTER TABLE framebyframe.albumnesia_game_sets DROP COLUMN game_version;
        ALTER TABLE framebyframe.albumnesia_attempts
            DROP CONSTRAINT albumnesia_score_scale_allowed,
            ADD CONSTRAINT albumnesia_score_scale_allowed CHECK (score_scale IN (50.00, 250.00));
    """)
