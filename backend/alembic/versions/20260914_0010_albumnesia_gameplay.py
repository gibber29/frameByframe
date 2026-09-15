"""Add persistent Albumnesia daily and room gameplay.

Revision ID: 20260914_0010
Revises: 20260914_0009
Create Date: 2026-09-14
"""

from alembic import op

revision = "20260914_0010"
down_revision = "20260914_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE framebyframe.albumnesia_game_sets (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            kind varchar(16) NOT NULL CONSTRAINT albumnesia_set_kind_allowed CHECK (kind IN ('daily', 'room')),
            game_date date,
            expires_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT albumnesia_set_date_shape CHECK (
                (kind = 'daily' AND game_date IS NOT NULL) OR
                (kind = 'room' AND game_date IS NULL)
            )
        );
        CREATE UNIQUE INDEX albumnesia_daily_set_date_unique
            ON framebyframe.albumnesia_game_sets (game_date) WHERE kind = 'daily';

        CREATE TABLE framebyframe.albumnesia_game_rounds (
            game_set_id uuid NOT NULL REFERENCES framebyframe.albumnesia_game_sets(id) ON DELETE CASCADE,
            round_number smallint NOT NULL CONSTRAINT albumnesia_round_number_range CHECK (round_number BETWEEN 1 AND 5),
            content_id uuid REFERENCES framebyframe.content_entries(id) ON DELETE SET NULL,
            title_snapshot text NOT NULL,
            normalized_answer_snapshot text NOT NULL,
            alternative_answers_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
            artist_snapshot text NOT NULL,
            release_year_snapshot smallint,
            recognizable_track_snapshot text NOT NULL,
            artist_initials_snapshot varchar(30) NOT NULL,
            image_key_snapshot text NOT NULL,
            distortion varchar(40) NOT NULL CONSTRAINT albumnesia_round_distortion_allowed CHECK (
                distortion IN ('pixel_hangover', 'sleeve_shredder', 'channel_damage', 'identity_crisis', 'outline_only')
            ),
            distortion_seed bigint NOT NULL,
            text_mask_regions_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
            subject_mask_regions_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
            PRIMARY KEY (game_set_id, round_number)
        );
        CREATE INDEX albumnesia_game_round_content_idx ON framebyframe.albumnesia_game_rounds(content_id);

        CREATE TABLE framebyframe.albumnesia_rooms (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            game_set_id uuid NOT NULL UNIQUE REFERENCES framebyframe.albumnesia_game_sets(id) ON DELETE CASCADE,
            code citext NOT NULL UNIQUE CONSTRAINT albumnesia_room_code_not_blank CHECK (btrim(code::text) <> ''),
            name varchar(80) NOT NULL CONSTRAINT albumnesia_room_name_not_blank CHECK (btrim(name) <> ''),
            allow_retries boolean NOT NULL DEFAULT false,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX albumnesia_rooms_expiry_idx ON framebyframe.albumnesia_rooms(expires_at);

        CREATE TABLE framebyframe.albumnesia_participants (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            room_id uuid NOT NULL REFERENCES framebyframe.albumnesia_rooms(id) ON DELETE CASCADE,
            guest_id uuid NOT NULL,
            display_name varchar(40) NOT NULL CONSTRAINT albumnesia_display_name_not_blank CHECK (btrim(display_name) <> ''),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT albumnesia_one_participant_per_guest UNIQUE (room_id, guest_id)
        );
        CREATE INDEX albumnesia_participants_room_idx ON framebyframe.albumnesia_participants(room_id, created_at);

        CREATE TABLE framebyframe.albumnesia_attempts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            game_set_id uuid NOT NULL REFERENCES framebyframe.albumnesia_game_sets(id) ON DELETE CASCADE,
            participant_id uuid REFERENCES framebyframe.albumnesia_participants(id) ON DELETE CASCADE,
            guest_id uuid NOT NULL,
            mode varchar(16) NOT NULL CONSTRAINT albumnesia_attempt_mode_allowed CHECK (mode IN ('daily', 'room')),
            status varchar(16) NOT NULL DEFAULT 'playing' CONSTRAINT albumnesia_attempt_status_allowed CHECK (status IN ('playing', 'completed', 'expired')),
            current_round smallint NOT NULL DEFAULT 1 CONSTRAINT albumnesia_attempt_round_range CHECK (current_round BETWEEN 1 AND 5),
            phase varchar(16) NOT NULL DEFAULT 'ready' CONSTRAINT albumnesia_attempt_phase_allowed CHECK (phase IN ('ready', 'memorize', 'guess', 'feedback', 'results')),
            phase_started_at timestamptz,
            phase_deadline timestamptz,
            correct_count smallint NOT NULL DEFAULT 0 CONSTRAINT albumnesia_correct_count_range CHECK (correct_count BETWEEN 0 AND 5),
            total_score numeric(8,2) NOT NULL DEFAULT 0.00 CONSTRAINT albumnesia_total_score_range CHECK (total_score BETWEEN 0 AND 250),
            total_answer_ms integer NOT NULL DEFAULT 0 CONSTRAINT albumnesia_total_answer_ms_nonnegative CHECK (total_answer_ms >= 0),
            started_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX albumnesia_daily_attempt_unique
            ON framebyframe.albumnesia_attempts(game_set_id, guest_id) WHERE mode = 'daily';
        CREATE UNIQUE INDEX albumnesia_room_attempt_unique
            ON framebyframe.albumnesia_attempts(participant_id) WHERE mode = 'room';

        CREATE TABLE framebyframe.albumnesia_round_submissions (
            attempt_id uuid NOT NULL REFERENCES framebyframe.albumnesia_attempts(id) ON DELETE CASCADE,
            round_number smallint NOT NULL CONSTRAINT albumnesia_submission_round_range CHECK (round_number BETWEEN 1 AND 5),
            submitted_title text,
            is_correct boolean NOT NULL,
            remaining_ms integer NOT NULL CONSTRAINT albumnesia_remaining_ms_range CHECK (remaining_ms BETWEEN 0 AND 5000),
            answer_time_ms integer NOT NULL CONSTRAINT albumnesia_answer_time_ms_range CHECK (answer_time_ms BETWEEN 0 AND 5000),
            awarded_score numeric(8,2) NOT NULL CONSTRAINT albumnesia_round_score_range CHECK (awarded_score BETWEEN 0 AND 50),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (attempt_id, round_number)
        );

        CREATE TABLE framebyframe.albumnesia_daily_progress (
            guest_id uuid PRIMARY KEY,
            current_streak integer NOT NULL DEFAULT 0 CONSTRAINT albumnesia_current_streak_nonnegative CHECK (current_streak >= 0),
            longest_streak integer NOT NULL DEFAULT 0 CONSTRAINT albumnesia_longest_streak_nonnegative CHECK (longest_streak >= 0),
            last_completed_date date,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE framebyframe.albumnesia_daily_progress;
        DROP TABLE framebyframe.albumnesia_round_submissions;
        DROP TABLE framebyframe.albumnesia_attempts;
        DROP TABLE framebyframe.albumnesia_participants;
        DROP TABLE framebyframe.albumnesia_rooms;
        DROP TABLE framebyframe.albumnesia_game_rounds;
        DROP TABLE framebyframe.albumnesia_game_sets;
    """)
