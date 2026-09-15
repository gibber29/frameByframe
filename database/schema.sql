-- REFERENCE SNAPSHOT ONLY. Alembic migrations own schema creation and changes.
-- This file is intentionally not mounted into PostgreSQL's init directory.
BEGIN;

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
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURNS NULL ON NULL INPUT
AS $$
    SELECT regexp_replace(lower(value), '[^a-z0-9]+', '', 'g');
$$;

CREATE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name citext NOT NULL UNIQUE,
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    type category_type NOT NULL DEFAULT 'genre',
    is_playable boolean NOT NULL DEFAULT true,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE movies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    normalized_title text GENERATED ALWAYS AS (normalize_title(title)) STORED,
    release_year smallint CHECK (release_year BETWEEN 1888 AND 2200),
    type media_type NOT NULL DEFAULT 'movie',
    status content_status NOT NULL DEFAULT 'ready',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT movies_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT movies_identity_unique UNIQUE (normalized_title, release_year, type)
);

CREATE TABLE movie_categories (
    movie_id uuid NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    category_id uuid NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, category_id)
);

CREATE TABLE reveal_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name citext NOT NULL UNIQUE,
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reveal_stages (
    profile_id uuid NOT NULL REFERENCES reveal_profiles(id) ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 10),
    radius_percent numeric(5,2) CHECK (radius_percent > 0 AND radius_percent <= 100),
    duration_ms integer CHECK (duration_ms > 0 AND duration_ms <= 10000),
    show_full_image boolean NOT NULL DEFAULT false,
    PRIMARY KEY (profile_id, round_number),
    CONSTRAINT full_stage_shape CHECK (
        (show_full_image AND radius_percent IS NULL)
        OR
        (NOT show_full_image AND radius_percent IS NOT NULL)
    )
);

CREATE TABLE rule_sets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name citext NOT NULL UNIQUE,
    base_score numeric(8,2) NOT NULL DEFAULT 1000.00 CHECK (base_score > 0),
    max_score numeric(8,2) NOT NULL DEFAULT 1000.00 CHECK (max_score > 0),
    time_penalty_per_second numeric(8,2) NOT NULL DEFAULT 5 CHECK (time_penalty_per_second >= 0),
    replay_penalty numeric(8,2) NOT NULL DEFAULT 0.00 CHECK (replay_penalty >= 0),
    cryptic_hint_penalty numeric(8,2) NOT NULL DEFAULT 50.00 CHECK (cryptic_hint_penalty >= 0),
    title_pattern_penalty numeric(8,2) NOT NULL DEFAULT 100.00 CHECK (title_pattern_penalty >= 0),
    minimum_correct_score numeric(8,2) NOT NULL DEFAULT 100.00 CHECK (minimum_correct_score >= 0),
    max_attempts smallint NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 10),
    score_decimal_places smallint NOT NULL DEFAULT 0 CHECK (score_decimal_places BETWEEN 0 AND 2),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT minimum_not_above_base CHECK (minimum_correct_score <= base_score)
);

CREATE TABLE rule_set_wrong_guess_penalties (
    rule_set_id uuid NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 5),
    hints_used_count smallint NOT NULL CHECK (hints_used_count BETWEEN 0 AND 2),
    penalty_amount numeric(8,2) NOT NULL CHECK (penalty_amount >= 0),
    PRIMARY KEY (rule_set_id, round_number, hints_used_count)
);

CREATE TABLE puzzles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id uuid NOT NULL REFERENCES movies(id) ON DELETE RESTRICT,
    image_key text NOT NULL UNIQUE,
    cryptic_hint text NOT NULL CHECK (btrim(cryptic_hint) <> ''),
    difficulty smallint NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),
    reveal_profile_id uuid NOT NULL REFERENCES reveal_profiles(id) ON DELETE RESTRICT,
    status content_status NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE puzzle_stage_regions (
    puzzle_id uuid NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 4),
    reveal_x numeric(5,2) NOT NULL CHECK (reveal_x BETWEEN 0 AND 100),
    reveal_y numeric(5,2) NOT NULL CHECK (reveal_y BETWEEN 0 AND 100),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (puzzle_id, round_number)
);

CREATE TABLE puzzle_categories (
    puzzle_id uuid NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
    category_id uuid NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (puzzle_id, category_id)
);

CREATE TABLE puzzle_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    puzzle_id uuid NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
    event message_event NOT NULL,
    message text NOT NULL CHECK (btrim(message) <> ''),
    expected_wrong_movie_id uuid REFERENCES movies(id) ON DELETE SET NULL,
    priority smallint NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE content_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category varchar(40) NOT NULL CHECK (category IN ('badly_explained', 'albumnesia', 'guess_assemble')),
    primary_answer text NOT NULL CHECK (btrim(primary_answer) <> ''),
    normalized_answer text GENERATED ALWAYS AS (normalize_title(primary_answer)) STORED,
    alternative_answers jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(alternative_answers) = 'array'),
    image_key text NOT NULL UNIQUE,
    difficulty smallint NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX content_entries_filters_idx ON content_entries(category, is_active, difficulty);
CREATE INDEX content_entries_answer_idx ON content_entries(normalized_answer);

CREATE TABLE badly_explained_content (
    content_id uuid PRIMARY KEY REFERENCES content_entries(id) ON DELETE CASCADE,
    clues jsonb NOT NULL CHECK (jsonb_typeof(clues) = 'array' AND jsonb_array_length(clues) = 4)
);

CREATE TABLE albumnesia_content (
    content_id uuid PRIMARY KEY REFERENCES content_entries(id) ON DELETE CASCADE,
    artist text NOT NULL,
    release_year smallint CHECK (release_year IS NULL OR release_year BETWEEN 1888 AND 2200),
    recognizable_track text NOT NULL,
    artist_initials varchar(30) NOT NULL,
    enabled_distortions jsonb NOT NULL CHECK (
        jsonb_typeof(enabled_distortions) = 'array'
        AND enabled_distortions <@ '["pixel_hangover", "sleeve_shredder", "channel_damage", "identity_crisis", "outline_only"]'::jsonb
    ),
    text_mask_regions jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(text_mask_regions) = 'array'
        AND NOT jsonb_path_exists(text_mask_regions, '$[*].points[*] ? (@.x < 0 || @.x > 1 || @.y < 0 || @.y > 1)')
    ),
    subject_mask_regions jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(subject_mask_regions) = 'array'
        AND NOT jsonb_path_exists(subject_mask_regions, '$[*].points[*] ? (@.x < 0 || @.x > 1 || @.y < 0 || @.y > 1)')
    )
);

-- Albumnesia gameplay snapshots are intentionally independent from mutable
-- catalogue metadata so published dailies and shared rooms remain reproducible.
CREATE TABLE albumnesia_game_sets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind varchar(16) NOT NULL CHECK (kind IN ('daily', 'room')),
    game_date date,
    game_version smallint NOT NULL DEFAULT 2 CHECK (game_version > 0),
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((kind = 'daily' AND game_date IS NOT NULL) OR (kind = 'room' AND game_date IS NULL))
);
CREATE UNIQUE INDEX albumnesia_daily_set_date_version_unique ON albumnesia_game_sets(game_date, game_version) WHERE kind = 'daily';

CREATE TABLE albumnesia_game_rounds (
    game_set_id uuid NOT NULL REFERENCES albumnesia_game_sets(id) ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 5),
    content_id uuid REFERENCES content_entries(id) ON DELETE SET NULL,
    title_snapshot text NOT NULL,
    normalized_answer_snapshot text NOT NULL,
    alternative_answers_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    artist_snapshot text NOT NULL,
    release_year_snapshot smallint,
    recognizable_track_snapshot text NOT NULL,
    artist_initials_snapshot varchar(30) NOT NULL,
    image_key_snapshot text NOT NULL,
    distortion varchar(40) NOT NULL CHECK (distortion IN ('pixel_hangover', 'sleeve_shredder', 'channel_damage', 'identity_crisis', 'outline_only')),
    distortion_seed bigint NOT NULL,
    text_mask_regions_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    subject_mask_regions_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (game_set_id, round_number)
);
CREATE INDEX albumnesia_game_round_content_idx ON albumnesia_game_rounds(content_id);

CREATE TABLE albumnesia_rooms (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_set_id uuid NOT NULL UNIQUE REFERENCES albumnesia_game_sets(id) ON DELETE CASCADE,
    code citext NOT NULL UNIQUE CHECK (btrim(code::text) <> ''),
    name varchar(80) NOT NULL CHECK (btrim(name) <> ''),
    host_display_name varchar(40) NOT NULL CHECK (btrim(host_display_name) <> ''),
    status varchar(16) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'expired')),
    allow_retries boolean NOT NULL DEFAULT false,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX albumnesia_rooms_expiry_idx ON albumnesia_rooms(expires_at);

CREATE TABLE albumnesia_participants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id uuid NOT NULL REFERENCES albumnesia_rooms(id) ON DELETE CASCADE,
    guest_id uuid NOT NULL,
    display_name varchar(40) NOT NULL CHECK (btrim(display_name) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (room_id, guest_id)
);
CREATE INDEX albumnesia_participants_room_idx ON albumnesia_participants(room_id, created_at);

CREATE TABLE albumnesia_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_set_id uuid NOT NULL REFERENCES albumnesia_game_sets(id) ON DELETE CASCADE,
    participant_id uuid REFERENCES albumnesia_participants(id) ON DELETE CASCADE,
    guest_id uuid NOT NULL,
    mode varchar(16) NOT NULL CHECK (mode IN ('daily', 'room')),
    status varchar(16) NOT NULL DEFAULT 'playing' CHECK (status IN ('playing', 'completed', 'expired')),
    current_round smallint NOT NULL DEFAULT 1 CHECK (current_round BETWEEN 1 AND 5),
    phase varchar(16) NOT NULL DEFAULT 'ready' CHECK (phase IN ('ready', 'memorize', 'guess', 'feedback', 'results')),
    phase_started_at timestamptz,
    phase_deadline timestamptz,
    correct_count smallint NOT NULL DEFAULT 0 CHECK (correct_count BETWEEN 0 AND 5),
    total_score numeric(8,2) NOT NULL DEFAULT 0.00,
    score_scale numeric(8,2) NOT NULL DEFAULT 50.00 CHECK (score_scale IN (10.00, 50.00, 250.00)),
    total_answer_ms integer NOT NULL DEFAULT 0 CHECK (total_answer_ms >= 0),
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (total_score BETWEEN 0 AND score_scale)
);
CREATE UNIQUE INDEX albumnesia_daily_attempt_unique ON albumnesia_attempts(game_set_id, guest_id) WHERE mode = 'daily';
CREATE UNIQUE INDEX albumnesia_room_attempt_unique ON albumnesia_attempts(participant_id) WHERE mode = 'room';

CREATE TABLE albumnesia_round_submissions (
    attempt_id uuid NOT NULL REFERENCES albumnesia_attempts(id) ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 5),
    submitted_title text,
    is_correct boolean NOT NULL,
    remaining_ms integer NOT NULL CHECK (remaining_ms BETWEEN 0 AND 5000),
    answer_time_ms integer NOT NULL CHECK (answer_time_ms BETWEEN 0 AND 5000),
    awarded_score numeric(8,2) NOT NULL CHECK (awarded_score BETWEEN 0 AND 50),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (attempt_id, round_number)
);

CREATE TABLE albumnesia_daily_progress (
    guest_id uuid PRIMARY KEY,
    current_streak integer NOT NULL DEFAULT 0 CHECK (current_streak >= 0),
    longest_streak integer NOT NULL DEFAULT 0 CHECK (longest_streak >= 0),
    last_completed_date date,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE daily_puzzles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    puzzle_id uuid NOT NULL REFERENCES puzzles(id) ON DELETE RESTRICT,
    category_id uuid NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    rule_set_id uuid NOT NULL REFERENCES rule_sets(id) ON DELETE RESTRICT,
    puzzle_date date NOT NULL,
    publish_at timestamptz,
    close_at timestamptz,
    status publication_status NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT valid_publication_window CHECK (
        close_at IS NULL OR publish_at IS NULL OR close_at > publish_at
    )
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username citext NOT NULL UNIQUE CHECK (char_length(username) BETWEEN 3 AND 30),
    email citext UNIQUE,
    avatar_url text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE game_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    daily_puzzle_id uuid NOT NULL REFERENCES daily_puzzles(id) ON DELETE RESTRICT,
    rule_set_id uuid NOT NULL REFERENCES rule_sets(id) ON DELETE RESTRICT,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    guest_id uuid,
    status session_status NOT NULL DEFAULT 'playing',
    current_round smallint NOT NULL DEFAULT 1 CHECK (current_round BETWEEN 1 AND 10),
    wrong_guess_count smallint NOT NULL DEFAULT 0 CHECK (wrong_guess_count >= 0),
    replay_count smallint NOT NULL DEFAULT 0 CHECK (replay_count >= 0),
    hint_used boolean NOT NULL DEFAULT false,
    cryptic_hint_used boolean NOT NULL DEFAULT false,
    title_pattern_used boolean NOT NULL DEFAULT false,
    cryptic_hint_unlocked_at timestamptz,
    title_pattern_unlocked_at timestamptz,
    guess_started_at timestamptz,
    solved_round smallint CHECK (solved_round BETWEEN 1 AND 5),
    active_guess_ms integer NOT NULL DEFAULT 0 CHECK (active_guess_ms >= 0),
    final_score numeric(8,2) CHECK (final_score >= 0),
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT session_has_player CHECK (user_id IS NOT NULL OR guest_id IS NOT NULL),
    CONSTRAINT completed_session_shape CHECK (
        (status = 'playing' AND completed_at IS NULL AND final_score IS NULL)
        OR
        (status <> 'playing' AND completed_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX one_registered_attempt_per_daily_puzzle
    ON game_sessions (daily_puzzle_id, user_id)
    WHERE user_id IS NOT NULL;

CREATE UNIQUE INDEX one_guest_attempt_per_daily_puzzle
    ON game_sessions (daily_puzzle_id, guest_id)
    WHERE guest_id IS NOT NULL;

CREATE TABLE guesses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    round_number smallint NOT NULL CHECK (round_number BETWEEN 1 AND 10),
    submitted_title text NOT NULL CHECK (btrim(submitted_title) <> ''),
    normalized_submission text GENERATED ALWAYS AS (normalize_title(submitted_title)) STORED,
    is_correct boolean NOT NULL,
    response_time_ms integer NOT NULL CHECK (response_time_ms >= 0),
    applied_wrong_guess_penalty numeric(8,2) NOT NULL DEFAULT 0.00 CHECK (applied_wrong_guess_penalty >= 0),
    hints_used_count smallint NOT NULL DEFAULT 0 CHECK (hints_used_count BETWEEN 0 AND 2),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT one_guess_per_round UNIQUE (session_id, round_number)
);

CREATE TABLE session_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    event_type text NOT NULL CHECK (event_type IN ('glimpse_shown', 'glimpse_replayed', 'hint_unlocked')),
    round_number smallint CHECK (round_number BETWEEN 1 AND 10),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX movies_normalized_title_idx ON movies (normalized_title);
CREATE INDEX movie_categories_category_idx ON movie_categories (category_id, movie_id);
CREATE INDEX puzzles_movie_idx ON puzzles (movie_id);
CREATE INDEX puzzles_ready_idx ON puzzles (status) WHERE status = 'ready';
CREATE INDEX puzzle_categories_category_idx ON puzzle_categories (category_id, puzzle_id);
CREATE INDEX puzzle_messages_lookup_idx ON puzzle_messages (puzzle_id, event, is_active, priority DESC);
CREATE INDEX daily_puzzles_lookup_idx ON daily_puzzles (category_id, puzzle_date, status);
CREATE UNIQUE INDEX one_active_daily_puzzle_per_category ON daily_puzzles (category_id, puzzle_date)
    WHERE status IN ('scheduled', 'published');
CREATE INDEX game_sessions_user_history_idx ON game_sessions (user_id, started_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX game_sessions_daily_score_idx ON game_sessions (daily_puzzle_id, final_score DESC, completed_at)
    WHERE status = 'won';
CREATE INDEX guesses_session_idx ON guesses (session_id, round_number);
CREATE INDEX session_events_session_idx ON session_events (session_id, created_at);

CREATE TRIGGER categories_set_updated_at
BEFORE UPDATE ON categories
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER movies_set_updated_at
BEFORE UPDATE ON movies
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER puzzles_set_updated_at
BEFORE UPDATE ON puzzles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER puzzle_stage_regions_set_updated_at
BEFORE UPDATE ON puzzle_stage_regions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER daily_puzzles_set_updated_at
BEFORE UPDATE ON daily_puzzles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER game_sessions_set_updated_at
BEFORE UPDATE ON game_sessions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE VIEW daily_leaderboard AS
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
        ORDER BY round(gs.final_score / NULLIF(rs.base_score, 0) * 50.00, 2) DESC,
                 gs.active_guess_ms ASC, gs.completed_at ASC
    ) AS rank
FROM game_sessions gs
JOIN users u ON u.id = gs.user_id
JOIN rule_sets rs ON rs.id = gs.rule_set_id
WHERE gs.status = 'won' AND gs.final_score IS NOT NULL;

INSERT INTO categories (name, slug, type, is_playable)
VALUES
    ('Anime', 'anime', 'genre', true),
    ('Superheroes', 'superheroes', 'genre', true),
    ('Disney & Pixar', 'disney-pixar', 'collection', true),
    ('All-Time Greats', 'all-time-greats', 'collection', true),
    ('Marvel', 'marvel', 'universe', false),
    ('DC', 'dc', 'universe', false),
    ('Pixar', 'pixar', 'collection', false),
    ('Disney', 'disney', 'collection', false),
    ('Studio Ghibli', 'studio-ghibli', 'collection', false)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    type = EXCLUDED.type,
    is_playable = EXCLUDED.is_playable,
    is_active = true;

INSERT INTO reveal_profiles (name, description)
VALUES ('Default five-turn reveal', 'Four expanding timed circles followed by the complete frame.')
ON CONFLICT (name) DO NOTHING;

INSERT INTO reveal_stages (profile_id, round_number, radius_percent, duration_ms, show_full_image)
SELECT rp.id, stage.round_number, stage.radius_percent, stage.duration_ms, stage.show_full_image
FROM reveal_profiles rp
CROSS JOIN (
    VALUES
        (1::smallint, 14.00::numeric, 200, false),
        (2::smallint, 22.00::numeric, 300, false),
        (3::smallint, 32.00::numeric, 300, false),
        (4::smallint, 45.00::numeric, 400, false),
        (5::smallint, NULL::numeric, 500, true)
) AS stage(round_number, radius_percent, duration_ms, show_full_image)
WHERE rp.name = 'Default five-turn reveal'
ON CONFLICT (profile_id, round_number) DO NOTHING;

INSERT INTO rule_sets (
    name,
    base_score,
    max_score,
    time_penalty_per_second,
    replay_penalty,
    cryptic_hint_penalty,
    title_pattern_penalty,
    minimum_correct_score,
    max_attempts,
    score_decimal_places
)
VALUES ('Daily gameplay v1', 1000.00, 1000.00, 5.00, 0.00, 50.00, 100.00, 100.00, 5, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO rule_set_wrong_guess_penalties (rule_set_id, round_number, hints_used_count, penalty_amount)
SELECT rule_set.id, values.round_number, values.hints_used_count, values.penalty_amount
FROM rule_sets AS rule_set
CROSS JOIN (VALUES
    (1::smallint, 0::smallint, 100), (1::smallint, 1::smallint, 100), (1::smallint, 2::smallint, 100),
    (2::smallint, 0::smallint, 100), (2::smallint, 1::smallint, 100), (2::smallint, 2::smallint, 100),
    (3::smallint, 0::smallint, 125), (3::smallint, 1::smallint, 150), (3::smallint, 2::smallint, 175),
    (4::smallint, 0::smallint, 125), (4::smallint, 1::smallint, 150), (4::smallint, 2::smallint, 175),
    (5::smallint, 0::smallint, 125), (5::smallint, 1::smallint, 150), (5::smallint, 2::smallint, 175)
) AS values(round_number, hints_used_count, penalty_amount)
WHERE rule_set.name = 'Daily gameplay v1'
ON CONFLICT DO NOTHING;

INSERT INTO rule_sets (
    name, base_score, max_score, time_penalty_per_second, replay_penalty,
    cryptic_hint_penalty, title_pattern_penalty, minimum_correct_score, max_attempts,
    score_decimal_places
)
VALUES ('Daily gameplay v2', 50.00, 50.00, 0.05, 0.00, 2.50, 5.00, 0.00, 5, 2)
ON CONFLICT (name) DO NOTHING;

INSERT INTO rule_set_wrong_guess_penalties (rule_set_id, round_number, hints_used_count, penalty_amount)
SELECT rule_set.id, values.round_number, values.hints_used_count, values.penalty_amount
FROM rule_sets AS rule_set
CROSS JOIN (VALUES
    (1::smallint, 0::smallint, 3.00::numeric), (1::smallint, 1::smallint, 3.00::numeric), (1::smallint, 2::smallint, 3.00::numeric),
    (2::smallint, 0::smallint, 3.00::numeric), (2::smallint, 1::smallint, 3.00::numeric), (2::smallint, 2::smallint, 3.00::numeric),
    (3::smallint, 0::smallint, 4.00::numeric), (3::smallint, 1::smallint, 5.00::numeric), (3::smallint, 2::smallint, 6.00::numeric),
    (4::smallint, 0::smallint, 4.00::numeric), (4::smallint, 1::smallint, 5.00::numeric), (4::smallint, 2::smallint, 6.00::numeric),
    (5::smallint, 0::smallint, 4.00::numeric), (5::smallint, 1::smallint, 5.00::numeric), (5::smallint, 2::smallint, 6.00::numeric)
) AS values(round_number, hints_used_count, penalty_amount)
WHERE rule_set.name = 'Daily gameplay v2'
ON CONFLICT DO NOTHING;

INSERT INTO movies (title, release_year, type)
VALUES
    ('Ant-Man', 2015, 'movie'),
    ('Avengers: Endgame', 2019, 'movie'),
    ('Avengers: Infinity War', 2018, 'movie'),
    ('Black Panther', 2018, 'movie'),
    ('Captain America: The Winter Soldier', 2014, 'movie'),
    ('Captain America: Civil War', 2016, 'movie'),
    ('Deadpool & Wolverine', 2024, 'movie'),
    ('Doctor Strange', 2016, 'movie'),
    ('Guardians of the Galaxy', 2014, 'movie'),
    ('Guardians of the Galaxy Vol. 2', 2017, 'movie'),
    ('Iron Man', 2008, 'movie'),
    ('Loki', 2021, 'series'),
    ('Moon Knight', 2022, 'series'),
    ('Spider-Man: Brand New Day', 2026, 'movie'),
    ('Spider-Man: Homecoming', 2017, 'movie'),
    ('Spider-Man: No Way Home', 2021, 'movie')
ON CONFLICT (normalized_title, release_year, type) DO NOTHING;

INSERT INTO movie_categories (movie_id, category_id)
SELECT m.id, c.id
FROM movies m
CROSS JOIN categories c
WHERE c.slug IN ('superheroes', 'marvel')
  AND m.normalized_title IN (
      'antman',
      'avengersendgame',
      'avengersinfinitywar',
      'blackpanther',
      'captainamericathewintersoldier',
      'captainamericacivilwar',
      'deadpoolwolverine',
      'doctorstrange',
      'guardiansofthegalaxy',
      'guardiansofthegalaxyvol2',
      'ironman',
      'loki',
      'moonknight',
      'spidermanbrandnewday',
      'spidermanhomecoming',
      'spidermannowayhome'
  )
ON CONFLICT DO NOTHING;

-- Badly Explained gameplay snapshots, asynchronous rooms and attempts.
CREATE TABLE badly_game_sets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kind varchar(16) NOT NULL CHECK (kind IN ('daily','room')),
    game_date date, content_id uuid REFERENCES content_entries(id) ON DELETE SET NULL,
    title_snapshot text NOT NULL, normalized_answer_snapshot text NOT NULL,
    alternative_answers_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    clues_snapshot jsonb NOT NULL CHECK (jsonb_typeof(clues_snapshot)='array' AND jsonb_array_length(clues_snapshot)=4),
    image_key_snapshot text NOT NULL, expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((kind='daily' AND game_date IS NOT NULL) OR (kind='room' AND game_date IS NULL))
);
CREATE UNIQUE INDEX badly_daily_set_date_unique ON badly_game_sets(game_date) WHERE kind='daily';
CREATE TABLE badly_rooms (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), game_set_id uuid NOT NULL UNIQUE REFERENCES badly_game_sets(id) ON DELETE CASCADE,
    code citext NOT NULL UNIQUE, name varchar(80) NOT NULL, host_display_name varchar(40) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'open', expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE badly_participants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), room_id uuid NOT NULL REFERENCES badly_rooms(id) ON DELETE CASCADE,
    guest_id uuid NOT NULL, display_name varchar(40) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(room_id,guest_id)
);
CREATE TABLE badly_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), game_set_id uuid NOT NULL REFERENCES badly_game_sets(id) ON DELETE CASCADE,
    participant_id uuid REFERENCES badly_participants(id) ON DELETE CASCADE, guest_id uuid NOT NULL,
    mode varchar(16) NOT NULL, status varchar(16) NOT NULL DEFAULT 'playing', phase varchar(16) NOT NULL DEFAULT 'ready',
    current_round smallint NOT NULL DEFAULT 1, phase_deadline timestamptz, successful_round smallint,
    successful_remaining_ms integer, started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX badly_daily_attempt_unique ON badly_attempts(game_set_id,guest_id) WHERE mode='daily';
CREATE UNIQUE INDEX badly_room_attempt_unique ON badly_attempts(participant_id) WHERE mode='room';
CREATE TABLE badly_submissions (
    attempt_id uuid NOT NULL REFERENCES badly_attempts(id) ON DELETE CASCADE, round_number smallint NOT NULL,
    submitted_title text, is_correct boolean NOT NULL, remaining_ms integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(attempt_id,round_number)
);
CREATE TABLE badly_daily_progress (
    guest_id uuid PRIMARY KEY, current_streak integer NOT NULL DEFAULT 0, longest_streak integer NOT NULL DEFAULT 0,
    last_completed_date date, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
