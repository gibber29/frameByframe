"""Store reveal coordinates per puzzle stage.

Revision ID: 20260912_0004
Revises: 20260912_0003
Create Date: 2026-09-12
"""

from alembic import op

revision = "20260912_0004"
down_revision = "20260912_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE framebyframe.puzzle_stage_regions (
            puzzle_id uuid NOT NULL REFERENCES framebyframe.puzzles(id) ON DELETE CASCADE,
            round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 4),
            reveal_x numeric(5,2) NOT NULL CHECK (reveal_x BETWEEN 0 AND 100),
            reveal_y numeric(5,2) NOT NULL CHECK (reveal_y BETWEEN 0 AND 100),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (puzzle_id, round_number)
        );

        INSERT INTO framebyframe.puzzle_stage_regions (puzzle_id, round_number, reveal_x, reveal_y)
        SELECT puzzle.id, round_number, puzzle.reveal_x, puzzle.reveal_y
        FROM framebyframe.puzzles AS puzzle
        CROSS JOIN generate_series(1, 4) AS round_number;

        CREATE TRIGGER puzzle_stage_regions_set_updated_at
        BEFORE UPDATE ON framebyframe.puzzle_stage_regions
        FOR EACH ROW EXECUTE FUNCTION framebyframe.set_updated_at();

        ALTER TABLE framebyframe.puzzles DROP COLUMN reveal_x;
        ALTER TABLE framebyframe.puzzles DROP COLUMN reveal_y;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE framebyframe.puzzles ADD COLUMN reveal_x numeric(5,2);
        ALTER TABLE framebyframe.puzzles ADD COLUMN reveal_y numeric(5,2);

        UPDATE framebyframe.puzzles AS puzzle
        SET reveal_x = COALESCE(region.reveal_x, 50.00),
            reveal_y = COALESCE(region.reveal_y, 50.00)
        FROM (
            SELECT puzzle_id, reveal_x, reveal_y
            FROM framebyframe.puzzle_stage_regions
            WHERE round_number = 1
        ) AS region
        WHERE region.puzzle_id = puzzle.id;

        UPDATE framebyframe.puzzles SET reveal_x = 50.00, reveal_y = 50.00
        WHERE reveal_x IS NULL OR reveal_y IS NULL;
        ALTER TABLE framebyframe.puzzles ALTER COLUMN reveal_x SET NOT NULL;
        ALTER TABLE framebyframe.puzzles ALTER COLUMN reveal_y SET NOT NULL;
        ALTER TABLE framebyframe.puzzles ADD CONSTRAINT puzzles_reveal_x_check CHECK (reveal_x BETWEEN 0 AND 100);
        ALTER TABLE framebyframe.puzzles ADD CONSTRAINT puzzles_reveal_y_check CHECK (reveal_y BETWEEN 0 AND 100);

        DROP TABLE framebyframe.puzzle_stage_regions;
        """
    )
