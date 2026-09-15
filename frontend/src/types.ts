export type HintState = 'locked' | 'available' | 'used'

export interface Category {
  slug: string
  name: string
}

export interface GameState {
  session_id: string
  category: string
  status: 'playing' | 'won' | 'lost' | 'expired'
  current_round: number
  maximum_rounds: number
  reveal_duration_ms: number
  reveal_radius_percent: string | null
  show_full_image: boolean
  hints_available: boolean
  cryptic_hint_state: HintState
  title_pattern_hint_state: HintState
  image_url: string
  glimpse_consumed: boolean
  guess_available_at: string | null
  score_estimate: string
  score_scale: string
  time_penalty_per_second: string
  cryptic_hint_penalty: string
  title_pattern_hint_penalty: string
}

export interface Glimpse {
  round_number: number
  countdown_ms: number
  duration_ms: number
  radius_percent: string | null
  show_full_image: boolean
  reveal_x: string | null
  reveal_y: string | null
  image_url: string
}

export interface Hint {
  kind: 'cryptic' | 'title-pattern'
  value: string
  penalty: string
  newly_unlocked: boolean
}

export interface WrongGuess {
  round_number: number
  submitted_title: string
  response_time_ms: number
  applied_wrong_guess_penalty: string
  raw_applied_wrong_guess_penalty: string
  hints_used_count: number
}

export interface GameResult {
  status: 'won' | 'lost'
  canonical_movie_title: string
  final_score: string
  raw_final_score: string
  raw_score_scale: string
  score_scale: string
  solved_round: number | null
  wrong_guesses: WrongGuess[]
  active_guess_ms: number
  cryptic_hint_used: boolean
  title_pattern_used: boolean
  total_hint_penalty: string
  time_penalty: string
  full_image_url: string
  message: string | null
}

export interface GuessOutcome {
  correct: boolean
  applied_wrong_guess_penalty: string
  raw_applied_wrong_guess_penalty: string
  state: GameState | null
  result: GameResult | null
}

export type AlbumPhase = 'ready' | 'memorize' | 'guess' | 'feedback' | 'results'

export interface AlbumClues {
  artist_initials: string
  release_year: number | null
  recognizable_track: string
}

export interface AlbumRoundResult {
  round_number: number
  title: string
  artist: string
  submitted_title: string | null
  correct: boolean
  score: string
  answer_time_ms: number
}

export interface AlbumAttempt {
  attempt_id: string
  mode: 'daily' | 'room'
  room_code: string | null
  status: 'playing' | 'completed' | 'expired'
  phase: AlbumPhase
  round_number: number
  total_rounds: number
  phase_deadline: string | null
  server_time: string
  image_url: string | null
  distortion: 'pixel_hangover' | 'sleeve_shredder' | 'channel_damage' | 'identity_crisis' | 'outline_only' | null
  distortion_seed: number | null
  text_mask_regions: MaskRegion[] | null
  subject_mask_regions: MaskRegion[] | null
  clues: AlbumClues | null
  revealed_title: string | null
  revealed_artist: string | null
  last_correct: boolean | null
  last_score: string | null
  correct_count: number
  total_score: string
  max_score: string
  legacy_score: boolean
  streak: number
  results: AlbumRoundResult[] | null
}

export interface MaskRegion { kind: string; points: { x: number; y: number }[] }
export interface AlbumHome { daily_date: string; active_album_count: number; daily_available: boolean; streak: number; completed_today: boolean }
export interface AlbumRoom { code: string; name: string; host_name: string; status: string; expires_at: string; participant_count: number; joined: boolean; current_player_name: string | null; attempt_id: string | null }
export interface LeaderboardEntry { display_name: string; finished: boolean; correct_count: number | null; score: string | null; answer_time_ms: number | null; average_response_ms: number | null; completed_at: string | null; is_current: boolean }
export interface AlbumLeaderboard { code: string; room_name: string; entries: LeaderboardEntry[] }

export interface BadlyResult { title:string; image_url:string; successful_round:number|null; remaining_ms:number; rank_value:number; daily_number:number|null; completed_at:string }
export interface BadlyState { attempt_id:string; mode:'daily'|'room'; room_code:string|null; lobby_name:string|null; status:string; phase:'ready'|'active'|'feedback'|'results'; round_number:number; deadline:string|null; server_time:string; current_hint:string|null; previous_hints:string[]; image_url:string|null; last_correct:boolean|null; streak:number; result:BadlyResult|null }
export interface BadlyHome { daily_date:string; active_count:number; daily_available:boolean; streak:number; completed_today:boolean }
export interface BadlyRoom { code:string; name:string; host_name:string; status:string; expires_at:string; participant_count:number; joined:boolean; current_player_name:string|null; attempt_id:string|null }
export interface BadlyLeader { display_name:string; finished:boolean; successful_round:number|null; remaining_ms:number|null; completed_at:string|null; is_current:boolean }
export interface BadlyBoard { code:string; room_name:string; entries:BadlyLeader[] }
