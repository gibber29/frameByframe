"""Create the initial FrameByFrame database schema.

Revision ID: 20260912_0001
Revises:
Create Date: 2026-09-12

The legacy-table check is intentionally narrow. It lets an existing Docker volume
created by database/schema.sql be adopted without replaying DDL. A partial legacy
schema is rejected instead of being silently accepted.
"""

from alembic import op
from sqlalchemy import inspect

revision = "20260912_0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "framebyframe"
TABLES = {
    "categories", "movies", "movie_categories", "reveal_profiles", "reveal_stages",
    "rule_sets", "puzzles", "puzzle_categories", "puzzle_messages", "daily_puzzles",
    "users", "game_sessions", "guesses", "session_events",
}


DDL = r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE SCHEMA IF NOT EXISTS framebyframe;
SET search_path TO framebyframe, public;

CREATE TYPE media_type AS ENUM ('movie', 'series');
CREATE TYPE category_type AS ENUM ('universe', 'genre', 'format', 'collection');
CREATE TYPE content_status AS ENUM ('draft', 'ready', 'archived');
CREATE TYPE publication_status AS ENUM ('draft', 'scheduled', 'published', 'cancelled');
CREATE TYPE session_status AS ENUM ('playing', 'won', 'lost', 'expired');
CREATE TYPE message_event AS ENUM ('wrong_guess', 'hint_used', 'solved_early', 'solved_late', 'failed');

CREATE FUNCTION normalize_title(value text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT
AS $$ SELECT regexp_replace(lower(value), '[^a-z0-9]+', '', 'g'); $$;

CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

CREATE TABLE categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name citext NOT NULL UNIQUE,
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    type category_type NOT NULL DEFAULT 'genre', is_playable boolean NOT NULL DEFAULT true,
    is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE movies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text NOT NULL,
    normalized_title text GENERATED ALWAYS AS (normalize_title(title)) STORED,
    release_year smallint CHECK (release_year BETWEEN 1888 AND 2200),
    type media_type NOT NULL DEFAULT 'movie', status content_status NOT NULL DEFAULT 'ready',
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT movies_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT movies_identity_unique UNIQUE (normalized_title, release_year, type)
);
CREATE TABLE movie_categories (
    movie_id uuid NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    category_id uuid NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, category_id)
);
CREATE TABLE reveal_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name citext NOT NULL UNIQUE,
    description text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE reveal_stages (
    profile_id uuid NOT NULL REFERENCES reveal_profiles(id) ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 10),
    radius_percent numeric(5,2) CHECK (radius_percent > 0 AND radius_percent <= 100),
    duration_ms integer CHECK (duration_ms > 0 AND duration_ms <= 10000),
    show_full_image boolean NOT NULL DEFAULT false, PRIMARY KEY (profile_id, round_number),
    CONSTRAINT full_stage_shape CHECK ((show_full_image AND radius_percent IS NULL) OR (NOT show_full_image AND radius_percent IS NOT NULL))
);
CREATE TABLE rule_sets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name citext NOT NULL UNIQUE,
    base_score integer NOT NULL DEFAULT 1000 CHECK (base_score > 0),
    wrong_guess_penalty integer NOT NULL DEFAULT 150 CHECK (wrong_guess_penalty >= 0),
    time_penalty_per_second numeric(8,2) NOT NULL DEFAULT 5 CHECK (time_penalty_per_second >= 0),
    replay_penalty integer NOT NULL DEFAULT 30 CHECK (replay_penalty >= 0),
    hint_penalty integer NOT NULL DEFAULT 125 CHECK (hint_penalty >= 0),
    minimum_correct_score integer NOT NULL DEFAULT 100 CHECK (minimum_correct_score >= 0),
    max_attempts smallint NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 10),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT minimum_not_above_base CHECK (minimum_correct_score <= base_score)
);
CREATE TABLE puzzles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), movie_id uuid NOT NULL REFERENCES movies(id) ON DELETE RESTRICT,
    image_key text NOT NULL UNIQUE, reveal_x numeric(5,2) NOT NULL CHECK (reveal_x BETWEEN 0 AND 100),
    reveal_y numeric(5,2) NOT NULL CHECK (reveal_y BETWEEN 0 AND 100),
    cryptic_hint text NOT NULL CHECK (btrim(cryptic_hint) <> ''),
    difficulty smallint NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),
    reveal_profile_id uuid NOT NULL REFERENCES reveal_profiles(id) ON DELETE RESTRICT,
    status content_status NOT NULL DEFAULT 'draft', created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE puzzle_categories (
    puzzle_id uuid NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
    category_id uuid NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (puzzle_id, category_id)
);
CREATE TABLE puzzle_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), puzzle_id uuid NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
    event message_event NOT NULL, message text NOT NULL CHECK (btrim(message) <> ''),
    expected_wrong_movie_id uuid REFERENCES movies(id) ON DELETE SET NULL,
    priority smallint NOT NULL DEFAULT 0, is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE daily_puzzles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), puzzle_id uuid NOT NULL REFERENCES puzzles(id) ON DELETE RESTRICT,
    category_id uuid NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    rule_set_id uuid NOT NULL REFERENCES rule_sets(id) ON DELETE RESTRICT,
    puzzle_date date NOT NULL, publish_at timestamptz, close_at timestamptz,
    status publication_status NOT NULL DEFAULT 'draft', created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT one_daily_puzzle_per_category UNIQUE (category_id, puzzle_date),
    CONSTRAINT valid_publication_window CHECK (close_at IS NULL OR publish_at IS NULL OR close_at > publish_at)
);
CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), username citext NOT NULL UNIQUE CHECK (char_length(username) BETWEEN 3 AND 30),
    email citext UNIQUE, avatar_url text, is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE game_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), daily_puzzle_id uuid NOT NULL REFERENCES daily_puzzles(id) ON DELETE RESTRICT,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL, guest_id uuid,
    status session_status NOT NULL DEFAULT 'playing', current_round smallint NOT NULL DEFAULT 1 CHECK (current_round BETWEEN 1 AND 10),
    wrong_guess_count smallint NOT NULL DEFAULT 0 CHECK (wrong_guess_count >= 0),
    replay_count smallint NOT NULL DEFAULT 0 CHECK (replay_count >= 0), hint_used boolean NOT NULL DEFAULT false,
    active_guess_ms integer NOT NULL DEFAULT 0 CHECK (active_guess_ms >= 0), final_score integer CHECK (final_score >= 0),
    started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT session_has_player CHECK (user_id IS NOT NULL OR guest_id IS NOT NULL),
    CONSTRAINT completed_session_shape CHECK ((status = 'playing' AND completed_at IS NULL AND final_score IS NULL) OR (status <> 'playing' AND completed_at IS NOT NULL))
);
CREATE UNIQUE INDEX one_registered_attempt_per_daily_puzzle ON game_sessions (daily_puzzle_id, user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX one_guest_attempt_per_daily_puzzle ON game_sessions (daily_puzzle_id, guest_id) WHERE guest_id IS NOT NULL;
CREATE TABLE guesses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), session_id uuid NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 10),
    submitted_title text NOT NULL CHECK (btrim(submitted_title) <> ''),
    normalized_submission text GENERATED ALWAYS AS (normalize_title(submitted_title)) STORED,
    is_correct boolean NOT NULL, response_time_ms integer NOT NULL CHECK (response_time_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT one_guess_per_round UNIQUE (session_id, round_number)
);
CREATE TABLE session_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, session_id uuid NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    event_type text NOT NULL CHECK (event_type IN ('glimpse_shown', 'glimpse_replayed', 'hint_unlocked')),
    round_number smallint CHECK (round_number BETWEEN 1 AND 10), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX movies_normalized_title_idx ON movies (normalized_title);
CREATE INDEX movie_categories_category_idx ON movie_categories (category_id, movie_id);
CREATE INDEX puzzles_movie_idx ON puzzles (movie_id);
CREATE INDEX puzzles_ready_idx ON puzzles (status) WHERE status = 'ready';
CREATE INDEX puzzle_categories_category_idx ON puzzle_categories (category_id, puzzle_id);
CREATE INDEX puzzle_messages_lookup_idx ON puzzle_messages (puzzle_id, event, is_active, priority DESC);
CREATE INDEX daily_puzzles_lookup_idx ON daily_puzzles (category_id, puzzle_date, status);
CREATE INDEX game_sessions_user_history_idx ON game_sessions (user_id, started_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX game_sessions_daily_score_idx ON game_sessions (daily_puzzle_id, final_score DESC, completed_at) WHERE status = 'won';
CREATE INDEX guesses_session_idx ON guesses (session_id, round_number);
CREATE INDEX session_events_session_idx ON session_events (session_id, created_at);
CREATE TRIGGER categories_set_updated_at BEFORE UPDATE ON categories FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER movies_set_updated_at BEFORE UPDATE ON movies FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER puzzles_set_updated_at BEFORE UPDATE ON puzzles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER daily_puzzles_set_updated_at BEFORE UPDATE ON daily_puzzles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER game_sessions_set_updated_at BEFORE UPDATE ON game_sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE VIEW daily_leaderboard AS
SELECT gs.daily_puzzle_id, gs.user_id, u.username, gs.final_score, gs.wrong_guess_count,
       gs.hint_used, gs.replay_count, gs.active_guess_ms, gs.completed_at,
       dense_rank() OVER (PARTITION BY gs.daily_puzzle_id ORDER BY gs.final_score DESC, gs.active_guess_ms ASC, gs.completed_at ASC) AS rank
FROM game_sessions gs JOIN users u ON u.id = gs.user_id
WHERE gs.status = 'won' AND gs.final_score IS NOT NULL;
"""


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    existing = set(inspector.get_table_names(schema=SCHEMA)) - {"alembic_version"}
    if existing:
        if existing != TABLES:
            missing = ", ".join(sorted(TABLES - existing))
            extra = ", ".join(sorted(existing - TABLES))
            raise RuntimeError(f"Refusing to adopt partial legacy schema (missing=[{missing}], extra=[{extra}])")
        return
    op.get_bind().exec_driver_sql(DDL)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS framebyframe CASCADE")
