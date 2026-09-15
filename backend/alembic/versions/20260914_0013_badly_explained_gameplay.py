"""Add player-facing Badly Explained daily and room gameplay.

Revision ID: 20260914_0013
Revises: 20260914_0012
"""
from alembic import op

revision = "20260914_0013"
down_revision = "20260914_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE framebyframe.badly_game_sets (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kind varchar(16) NOT NULL CHECK(kind IN ('daily','room')),
      game_date date, content_id uuid REFERENCES framebyframe.content_entries(id) ON DELETE SET NULL,
      title_snapshot text NOT NULL, normalized_answer_snapshot text NOT NULL,
      alternative_answers_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
      clues_snapshot jsonb NOT NULL CHECK(jsonb_typeof(clues_snapshot)='array' AND jsonb_array_length(clues_snapshot)=4),
      image_key_snapshot text NOT NULL, expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
      CHECK((kind='daily' AND game_date IS NOT NULL) OR (kind='room' AND game_date IS NULL))
    );
    CREATE UNIQUE INDEX badly_daily_set_date_unique ON framebyframe.badly_game_sets(game_date) WHERE kind='daily';
    CREATE TABLE framebyframe.badly_rooms (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), game_set_id uuid NOT NULL UNIQUE REFERENCES framebyframe.badly_game_sets(id) ON DELETE CASCADE,
      code citext NOT NULL UNIQUE, name varchar(80) NOT NULL CHECK(btrim(name)<>''), host_display_name varchar(40) NOT NULL CHECK(btrim(host_display_name)<>''),
      status varchar(16) NOT NULL DEFAULT 'open' CHECK(status IN ('open','expired')), expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE framebyframe.badly_participants (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), room_id uuid NOT NULL REFERENCES framebyframe.badly_rooms(id) ON DELETE CASCADE,
      guest_id uuid NOT NULL, display_name varchar(40) NOT NULL CHECK(btrim(display_name)<>''), created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(room_id,guest_id)
    );
    CREATE TABLE framebyframe.badly_attempts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), game_set_id uuid NOT NULL REFERENCES framebyframe.badly_game_sets(id) ON DELETE CASCADE,
      participant_id uuid REFERENCES framebyframe.badly_participants(id) ON DELETE CASCADE, guest_id uuid NOT NULL,
      mode varchar(16) NOT NULL CHECK(mode IN ('daily','room')), status varchar(16) NOT NULL DEFAULT 'playing' CHECK(status IN ('playing','completed','expired')),
      phase varchar(16) NOT NULL DEFAULT 'ready' CHECK(phase IN ('ready','active','feedback','results')),
      current_round smallint NOT NULL DEFAULT 1 CHECK(current_round BETWEEN 1 AND 5), phase_deadline timestamptz,
      successful_round smallint CHECK(successful_round BETWEEN 1 AND 5), successful_remaining_ms integer CHECK(successful_remaining_ms BETWEEN 0 AND 10000),
      started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX badly_daily_attempt_unique ON framebyframe.badly_attempts(game_set_id,guest_id) WHERE mode='daily';
    CREATE UNIQUE INDEX badly_room_attempt_unique ON framebyframe.badly_attempts(participant_id) WHERE mode='room';
    CREATE TABLE framebyframe.badly_submissions (
      attempt_id uuid NOT NULL REFERENCES framebyframe.badly_attempts(id) ON DELETE CASCADE, round_number smallint NOT NULL CHECK(round_number BETWEEN 1 AND 5),
      submitted_title text, is_correct boolean NOT NULL, remaining_ms integer NOT NULL CHECK(remaining_ms BETWEEN 0 AND 10000),
      created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(attempt_id,round_number)
    );
    CREATE TABLE framebyframe.badly_daily_progress (
      guest_id uuid PRIMARY KEY, current_streak integer NOT NULL DEFAULT 0 CHECK(current_streak>=0), longest_streak integer NOT NULL DEFAULT 0 CHECK(longest_streak>=0),
      last_completed_date date, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE framebyframe.badly_daily_progress, framebyframe.badly_submissions, framebyframe.badly_attempts, framebyframe.badly_participants, framebyframe.badly_rooms, framebyframe.badly_game_sets CASCADE")
