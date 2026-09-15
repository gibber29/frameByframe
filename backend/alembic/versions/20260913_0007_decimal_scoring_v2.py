"""Add decimal scoring and Daily gameplay v2.

Revision ID: 20260913_0007
Revises: 20260913_0006
Create Date: 2026-09-13
"""

from alembic import op

revision = "20260913_0007"
down_revision = "20260913_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DROP VIEW framebyframe.daily_leaderboard;

        ALTER TABLE framebyframe.rule_sets
            ALTER COLUMN base_score TYPE numeric(8,2) USING base_score::numeric(8,2),
            ALTER COLUMN base_score SET DEFAULT 1000.00,
            ALTER COLUMN replay_penalty TYPE numeric(8,2) USING replay_penalty::numeric(8,2),
            ALTER COLUMN replay_penalty SET DEFAULT 0.00,
            ALTER COLUMN cryptic_hint_penalty TYPE numeric(8,2) USING cryptic_hint_penalty::numeric(8,2),
            ALTER COLUMN cryptic_hint_penalty SET DEFAULT 50.00,
            ALTER COLUMN title_pattern_penalty TYPE numeric(8,2) USING title_pattern_penalty::numeric(8,2),
            ALTER COLUMN title_pattern_penalty SET DEFAULT 100.00,
            ALTER COLUMN minimum_correct_score TYPE numeric(8,2) USING minimum_correct_score::numeric(8,2),
            ALTER COLUMN minimum_correct_score SET DEFAULT 100.00,
            ADD COLUMN max_score numeric(8,2),
            ADD COLUMN score_decimal_places smallint NOT NULL DEFAULT 0
                CHECK (score_decimal_places BETWEEN 0 AND 2);

        UPDATE framebyframe.rule_sets SET max_score = base_score;
        ALTER TABLE framebyframe.rule_sets
            ALTER COLUMN max_score SET NOT NULL,
            ALTER COLUMN max_score SET DEFAULT 1000.00,
            ADD CONSTRAINT max_score_positive CHECK (max_score > 0);

        ALTER TABLE framebyframe.rule_set_wrong_guess_penalties
            ALTER COLUMN penalty_amount TYPE numeric(8,2) USING penalty_amount::numeric(8,2);

        ALTER TABLE framebyframe.guesses
            ALTER COLUMN applied_wrong_guess_penalty TYPE numeric(8,2)
                USING applied_wrong_guess_penalty::numeric(8,2),
            ALTER COLUMN applied_wrong_guess_penalty SET DEFAULT 0.00;

        ALTER TABLE framebyframe.game_sessions
            ALTER COLUMN final_score TYPE numeric(8,2) USING final_score::numeric(8,2),
            ADD COLUMN rule_set_id uuid;

        UPDATE framebyframe.game_sessions AS session
        SET rule_set_id = daily.rule_set_id
        FROM framebyframe.daily_puzzles AS daily
        WHERE daily.id = session.daily_puzzle_id;

        ALTER TABLE framebyframe.game_sessions
            ALTER COLUMN rule_set_id SET NOT NULL,
            ADD CONSTRAINT game_sessions_rule_set_id_fkey
                FOREIGN KEY (rule_set_id) REFERENCES framebyframe.rule_sets(id) ON DELETE RESTRICT;

        INSERT INTO framebyframe.rule_sets (
            name, base_score, max_score, time_penalty_per_second, replay_penalty,
            cryptic_hint_penalty, title_pattern_penalty, minimum_correct_score, max_attempts,
            score_decimal_places
        ) VALUES (
            'Daily gameplay v2', 50.00, 50.00, 0.05, 0.00,
            2.50, 5.00, 0.00, 5, 2
        );

        INSERT INTO framebyframe.rule_set_wrong_guess_penalties
            (rule_set_id, round_number, hints_used_count, penalty_amount)
        SELECT rule_set.id, values.round_number, values.hints_used_count, values.penalty_amount
        FROM framebyframe.rule_sets AS rule_set
        CROSS JOIN (VALUES
            (1::smallint, 0::smallint, 3.00::numeric), (1::smallint, 1::smallint, 3.00::numeric), (1::smallint, 2::smallint, 3.00::numeric),
            (2::smallint, 0::smallint, 3.00::numeric), (2::smallint, 1::smallint, 3.00::numeric), (2::smallint, 2::smallint, 3.00::numeric),
            (3::smallint, 0::smallint, 4.00::numeric), (3::smallint, 1::smallint, 5.00::numeric), (3::smallint, 2::smallint, 6.00::numeric),
            (4::smallint, 0::smallint, 4.00::numeric), (4::smallint, 1::smallint, 5.00::numeric), (4::smallint, 2::smallint, 6.00::numeric),
            (5::smallint, 0::smallint, 4.00::numeric), (5::smallint, 1::smallint, 5.00::numeric), (5::smallint, 2::smallint, 6.00::numeric)
        ) AS values(round_number, hints_used_count, penalty_amount)
        WHERE rule_set.name = 'Daily gameplay v2';

        CREATE VIEW framebyframe.daily_leaderboard AS
        SELECT
            gs.daily_puzzle_id,
            gs.user_id,
            u.username,
            gs.rule_set_id,
            gs.final_score,
            rs.base_score AS raw_score_scale,
            50.00::numeric(8,2) AS score_scale,
            round(gs.final_score / NULLIF(rs.base_score, 0) * 50.00, 2)::numeric(8,2) AS normalized_score,
            gs.wrong_guess_count,
            gs.hint_used,
            gs.replay_count,
            gs.active_guess_ms,
            gs.completed_at,
            dense_rank() OVER (
                PARTITION BY gs.daily_puzzle_id
                ORDER BY
                    round(gs.final_score / NULLIF(rs.base_score, 0) * 50.00, 2) DESC,
                    gs.active_guess_ms ASC,
                    gs.completed_at ASC
            ) AS rank
        FROM framebyframe.game_sessions AS gs
        JOIN framebyframe.users AS u ON u.id = gs.user_id
        JOIN framebyframe.rule_sets AS rs ON rs.id = gs.rule_set_id
        WHERE gs.status = 'won' AND gs.final_score IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP VIEW framebyframe.daily_leaderboard;

        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM framebyframe.game_sessions AS gs
                JOIN framebyframe.rule_sets AS rs ON rs.id = gs.rule_set_id
                WHERE rs.name = 'Daily gameplay v2'
            ) OR EXISTS (
                SELECT 1
                FROM framebyframe.daily_puzzles AS dp
                JOIN framebyframe.rule_sets AS rs ON rs.id = dp.rule_set_id
                WHERE rs.name = 'Daily gameplay v2'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while Daily gameplay v2 is referenced';
            END IF;
        END $$;

        DELETE FROM framebyframe.rule_sets WHERE name = 'Daily gameplay v2';

        ALTER TABLE framebyframe.game_sessions
            DROP CONSTRAINT game_sessions_rule_set_id_fkey,
            DROP COLUMN rule_set_id,
            ALTER COLUMN final_score TYPE integer USING round(final_score)::integer;

        ALTER TABLE framebyframe.guesses
            ALTER COLUMN applied_wrong_guess_penalty DROP DEFAULT,
            ALTER COLUMN applied_wrong_guess_penalty TYPE integer USING round(applied_wrong_guess_penalty)::integer,
            ALTER COLUMN applied_wrong_guess_penalty SET DEFAULT 0;

        ALTER TABLE framebyframe.rule_set_wrong_guess_penalties
            ALTER COLUMN penalty_amount TYPE integer USING round(penalty_amount)::integer;

        ALTER TABLE framebyframe.rule_sets
            DROP CONSTRAINT max_score_positive,
            DROP COLUMN max_score,
            DROP COLUMN score_decimal_places,
            ALTER COLUMN minimum_correct_score TYPE integer USING round(minimum_correct_score)::integer,
            ALTER COLUMN minimum_correct_score SET DEFAULT 100,
            ALTER COLUMN title_pattern_penalty TYPE integer USING round(title_pattern_penalty)::integer,
            ALTER COLUMN title_pattern_penalty SET DEFAULT 100,
            ALTER COLUMN cryptic_hint_penalty TYPE integer USING round(cryptic_hint_penalty)::integer,
            ALTER COLUMN cryptic_hint_penalty SET DEFAULT 50,
            ALTER COLUMN replay_penalty TYPE integer USING round(replay_penalty)::integer,
            ALTER COLUMN replay_penalty SET DEFAULT 0,
            ALTER COLUMN base_score TYPE integer USING round(base_score)::integer,
            ALTER COLUMN base_score SET DEFAULT 1000;

        CREATE VIEW framebyframe.daily_leaderboard AS
        SELECT gs.daily_puzzle_id, gs.user_id, u.username, gs.final_score,
               gs.wrong_guess_count, gs.hint_used, gs.replay_count,
               gs.active_guess_ms, gs.completed_at,
               dense_rank() OVER (
                   PARTITION BY gs.daily_puzzle_id
                   ORDER BY gs.final_score DESC, gs.active_guess_ms ASC, gs.completed_at ASC
               ) AS rank
        FROM framebyframe.game_sessions AS gs
        JOIN framebyframe.users AS u ON u.id = gs.user_id
        WHERE gs.status = 'won' AND gs.final_score IS NOT NULL;
        """
    )
