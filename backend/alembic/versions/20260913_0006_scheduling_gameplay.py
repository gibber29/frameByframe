"""Add versioned gameplay rules, hint state, and recorded guess penalties.

Revision ID: 20260913_0006
Revises: 20260912_0005
Create Date: 2026-09-13
"""

from alembic import op

revision = "20260913_0006"
down_revision = "20260912_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE framebyframe.rule_sets
            ADD COLUMN cryptic_hint_penalty integer NOT NULL DEFAULT 50 CHECK (cryptic_hint_penalty >= 0),
            ADD COLUMN title_pattern_penalty integer NOT NULL DEFAULT 100 CHECK (title_pattern_penalty >= 0);

        CREATE TABLE framebyframe.rule_set_wrong_guess_penalties (
            rule_set_id uuid NOT NULL REFERENCES framebyframe.rule_sets(id) ON DELETE CASCADE,
            round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 5),
            hints_used_count smallint NOT NULL CHECK (hints_used_count BETWEEN 0 AND 2),
            penalty_amount integer NOT NULL CHECK (penalty_amount >= 0),
            PRIMARY KEY (rule_set_id, round_number, hints_used_count)
        );

        INSERT INTO framebyframe.rule_set_wrong_guess_penalties
            (rule_set_id, round_number, hints_used_count, penalty_amount)
        SELECT rule_set.id, round_number, hints_used_count, rule_set.wrong_guess_penalty
        FROM framebyframe.rule_sets AS rule_set
        CROSS JOIN generate_series(1, 5) AS round_number
        CROSS JOIN generate_series(0, 2) AS hints_used_count;

        UPDATE framebyframe.rule_sets
        SET cryptic_hint_penalty = hint_penalty, title_pattern_penalty = 0;

        INSERT INTO framebyframe.rule_sets (
            name, base_score, wrong_guess_penalty, time_penalty_per_second,
            replay_penalty, hint_penalty, minimum_correct_score, max_attempts,
            cryptic_hint_penalty, title_pattern_penalty
        ) VALUES ('Daily gameplay v1', 1000, 0, 5, 0, 0, 100, 5, 50, 100);

        INSERT INTO framebyframe.rule_set_wrong_guess_penalties
            (rule_set_id, round_number, hints_used_count, penalty_amount)
        SELECT rule_set.id, values.round_number, values.hints_used_count, values.penalty_amount
        FROM framebyframe.rule_sets AS rule_set
        CROSS JOIN (VALUES
            (1::smallint, 0::smallint, 100), (1::smallint, 1::smallint, 100), (1::smallint, 2::smallint, 100),
            (2::smallint, 0::smallint, 100), (2::smallint, 1::smallint, 100), (2::smallint, 2::smallint, 100),
            (3::smallint, 0::smallint, 125), (3::smallint, 1::smallint, 150), (3::smallint, 2::smallint, 175),
            (4::smallint, 0::smallint, 125), (4::smallint, 1::smallint, 150), (4::smallint, 2::smallint, 175),
            (5::smallint, 0::smallint, 125), (5::smallint, 1::smallint, 150), (5::smallint, 2::smallint, 175)
        ) AS values(round_number, hints_used_count, penalty_amount)
        WHERE rule_set.name = 'Daily gameplay v1';

        ALTER TABLE framebyframe.rule_sets
            DROP COLUMN wrong_guess_penalty,
            DROP COLUMN hint_penalty;

        ALTER TABLE framebyframe.game_sessions
            ADD COLUMN cryptic_hint_used boolean NOT NULL DEFAULT false,
            ADD COLUMN title_pattern_used boolean NOT NULL DEFAULT false,
            ADD COLUMN cryptic_hint_unlocked_at timestamptz,
            ADD COLUMN title_pattern_unlocked_at timestamptz,
            ADD COLUMN guess_started_at timestamptz,
            ADD COLUMN solved_round smallint CHECK (solved_round BETWEEN 1 AND 5);

        ALTER TABLE framebyframe.guesses
            ADD COLUMN applied_wrong_guess_penalty integer NOT NULL DEFAULT 0 CHECK (applied_wrong_guess_penalty >= 0),
            ADD COLUMN hints_used_count smallint NOT NULL DEFAULT 0 CHECK (hints_used_count BETWEEN 0 AND 2);

        ALTER TABLE framebyframe.daily_puzzles DROP CONSTRAINT one_daily_puzzle_per_category;
        CREATE UNIQUE INDEX one_active_daily_puzzle_per_category
            ON framebyframe.daily_puzzles (category_id, puzzle_date)
            WHERE status IN ('scheduled', 'published');
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX framebyframe.one_active_daily_puzzle_per_category;
        ALTER TABLE framebyframe.daily_puzzles
            ADD CONSTRAINT one_daily_puzzle_per_category UNIQUE (category_id, puzzle_date);
        ALTER TABLE framebyframe.guesses
            DROP COLUMN hints_used_count,
            DROP COLUMN applied_wrong_guess_penalty;
        ALTER TABLE framebyframe.game_sessions
            DROP COLUMN solved_round,
            DROP COLUMN guess_started_at,
            DROP COLUMN title_pattern_unlocked_at,
            DROP COLUMN cryptic_hint_unlocked_at,
            DROP COLUMN title_pattern_used,
            DROP COLUMN cryptic_hint_used;
        ALTER TABLE framebyframe.rule_sets
            ADD COLUMN wrong_guess_penalty integer NOT NULL DEFAULT 150 CHECK (wrong_guess_penalty >= 0),
            ADD COLUMN hint_penalty integer NOT NULL DEFAULT 125 CHECK (hint_penalty >= 0);
        UPDATE framebyframe.rule_sets
            SET wrong_guess_penalty = 150, hint_penalty = cryptic_hint_penalty;
        DELETE FROM framebyframe.rule_sets WHERE name = 'Daily gameplay v1';
        DROP TABLE framebyframe.rule_set_wrong_guess_penalties;
        ALTER TABLE framebyframe.rule_sets
            DROP COLUMN title_pattern_penalty,
            DROP COLUMN cryptic_hint_penalty;
        """
    )
