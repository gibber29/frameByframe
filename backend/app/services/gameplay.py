import unicodedata
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.models.entities import GameSession, Guess, MessageEvent, SessionEvent, SessionStatus
from backend.app.repositories.game import GameRepository
from backend.app.schemas.game import (
    GameResultRead,
    GameStateRead,
    GlimpseRead,
    GuessOutcome,
    GuessResultRead,
    HintRead,
)

COUNTDOWN_MS = 1800
MAX_ROUNDS = 5
SCORE_QUANTUM = Decimal("0.01")


class GameNotFound(LookupError):
    pass


class GameConflict(ValueError):
    pass


def normalize_guess(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def title_pattern(title: str) -> str:
    return "".join("_" if character.isalnum() else character for character in title)


class GameplayService:
    def __init__(self, repository: GameRepository, timezone_name: str) -> None:
        self.repository = repository
        self.session = repository.session
        self.timezone = ZoneInfo(timezone_name)

    def now(self):
        return self.session.scalar(select(func.clock_timestamp()))

    def start(self, category_slug: str, guest_id: uuid.UUID) -> GameSession:
        now = self.now()
        daily = self.repository.published_daily(category_slug, now.astimezone(self.timezone).date(), now)
        if daily is None:
            raise GameNotFound("No published puzzle is available for this category today")
        existing = self.repository.find_guest_session(daily.id, guest_id)
        if existing is not None:
            return existing
        game = GameSession(daily_puzzle_id=daily.id, rule_set_id=daily.rule_set_id, guest_id=guest_id)
        self.session.add(game)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.repository.find_guest_session(daily.id, guest_id)
            if existing is None:
                raise
            return existing
        return self.repository.get_session(game.id, guest_id)  # type: ignore[return-value]

    def require_game(self, session_id: uuid.UUID, guest_id: uuid.UUID, lock: bool = False) -> GameSession:
        game = self.repository.get_session(session_id, guest_id, lock)
        if game is None:
            raise GameNotFound("Game session not found")
        return game

    @staticmethod
    def current_stage(game: GameSession):
        return next(stage for stage in game.daily_puzzle.puzzle.reveal_profile.stages if stage.round_number == game.current_round)

    @staticmethod
    def hint_states(game: GameSession) -> tuple[str, str]:
        cryptic = "used" if game.cryptic_hint_used else ("available" if game.current_round >= 3 else "locked")
        title = "used" if game.title_pattern_used else ("available" if game.current_round >= 3 and game.cryptic_hint_used else "locked")
        return cryptic, title

    def state(self, game: GameSession) -> GameStateRead:
        stage = self.current_stage(game)
        cryptic, title = self.hint_states(game)
        glimpse_consumed = self.repository.glimpse_exists(game.id, game.current_round)
        return GameStateRead(
            session_id=game.id,
            category=game.daily_puzzle.category.slug,
            status=game.status.value,
            current_round=game.current_round,
            maximum_rounds=MAX_ROUNDS,
            reveal_duration_ms=stage.duration_ms,
            reveal_radius_percent=stage.radius_percent,
            show_full_image=stage.show_full_image,
            hints_available=game.status == SessionStatus.PLAYING and game.current_round >= 3,
            cryptic_hint_state=cryptic,
            title_pattern_hint_state=title,
            image_url=f"/api/v1/game/{game.id}/image",
            glimpse_consumed=glimpse_consumed,
            guess_available_at=game.guess_started_at,
            score_estimate=self.normalize_score(
                game.final_score if game.final_score is not None else self.raw_score_estimate(game),
                game.rule_set,
            ),
            score_scale=Decimal("50.00"),
            time_penalty_per_second=self.normalize_score(
                game.rule_set.time_penalty_per_second, game.rule_set
            ),
            cryptic_hint_penalty=self.normalize_score(
                game.rule_set.cryptic_hint_penalty, game.rule_set
            ),
            title_pattern_hint_penalty=self.normalize_score(
                game.rule_set.title_pattern_penalty, game.rule_set
            ),
        )

    @staticmethod
    def round_score(value: Decimal, rules) -> Decimal:
        quantum = Decimal(1).scaleb(-rules.score_decimal_places)
        rounding = ROUND_HALF_UP if rules.score_decimal_places else ROUND_CEILING
        return value.quantize(quantum, rounding=rounding).quantize(SCORE_QUANTUM)

    @staticmethod
    def normalize_score(value: Decimal, rules) -> Decimal:
        return (value / rules.base_score * Decimal("50.00")).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)

    def raw_score_estimate(self, game: GameSession) -> Decimal:
        rules = game.rule_set
        wrong_penalties = sum(guess.applied_wrong_guess_penalty for guess in game.guesses if not guess.is_correct)
        active_ms = game.active_guess_ms
        if game.guess_started_at is not None:
            active_ms += max(0, int((self.now() - game.guess_started_at).total_seconds() * 1000))
        time_penalty = Decimal(active_ms) / Decimal(1000) * rules.time_penalty_per_second
        hint_penalty = (
            (rules.cryptic_hint_penalty if game.cryptic_hint_used else 0)
            + (rules.title_pattern_penalty if game.title_pattern_used else 0)
        )
        return self.round_score(max(
            rules.minimum_correct_score,
            rules.base_score - wrong_penalties - time_penalty - hint_penalty,
        ), rules)

    def glimpse(self, session_id: uuid.UUID, guest_id: uuid.UUID) -> GlimpseRead:
        game = self.require_game(session_id, guest_id, lock=True)
        if game.status != SessionStatus.PLAYING:
            raise GameConflict("The game is already complete")
        if self.repository.glimpse_exists(game.id, game.current_round):
            raise GameConflict("This round's glimpse has already been consumed")
        stage = self.current_stage(game)
        region = None
        if not stage.show_full_image:
            region = next((item for item in game.daily_puzzle.puzzle.stage_regions if item.round_number == game.current_round), None)
            if region is None:
                raise GameConflict("The current puzzle has no configured region for this round")
        now = self.now()
        game.guess_started_at = now + timedelta(milliseconds=COUNTDOWN_MS + stage.duration_ms)
        game.events.append(SessionEvent(event_type="glimpse_shown", round_number=game.current_round))
        self.session.commit()
        return GlimpseRead(
            round_number=game.current_round,
            countdown_ms=COUNTDOWN_MS,
            duration_ms=stage.duration_ms,
            radius_percent=stage.radius_percent,
            show_full_image=stage.show_full_image,
            reveal_x=region.reveal_x if region else None,
            reveal_y=region.reveal_y if region else None,
            image_url=f"/api/v1/game/{game.id}/image",
        )

    def guess(self, session_id: uuid.UUID, guest_id: uuid.UUID, submitted_title: str) -> GuessOutcome:
        game = self.require_game(session_id, guest_id, lock=True)
        if game.status != SessionStatus.PLAYING:
            raise GameConflict("The game is already complete")
        if not self.repository.glimpse_exists(game.id, game.current_round) or game.guess_started_at is None:
            raise GameConflict("Consume the current glimpse before guessing")
        now = self.now()
        if now < game.guess_started_at:
            raise GameConflict("The glimpse has not finished yet")
        if any(guess.round_number == game.current_round for guess in game.guesses):
            raise GameConflict("A guess has already been submitted for this round")

        response_time_ms = max(0, int((now - game.guess_started_at).total_seconds() * 1000))
        hints_used_count = int(game.cryptic_hint_used) + int(game.title_pattern_used)
        correct = normalize_guess(submitted_title) == normalize_guess(game.daily_puzzle.puzzle.movie.title)
        penalty = 0 if correct else self.repository.wrong_penalty(
            game.rule_set_id, game.current_round, hints_used_count
        )
        game.guesses.append(Guess(
            round_number=game.current_round,
            submitted_title=submitted_title.strip(),
            is_correct=correct,
            response_time_ms=response_time_ms,
            applied_wrong_guess_penalty=penalty,
            hints_used_count=hints_used_count,
        ))
        game.active_guess_ms += response_time_ms
        game.guess_started_at = None

        if correct:
            game.status = SessionStatus.WON
            game.solved_round = game.current_round
            game.completed_at = now
            self.session.flush()
            game.final_score = self.calculate_score(game)
        else:
            game.wrong_guess_count += 1
        if not correct and game.current_round == MAX_ROUNDS:
            game.status = SessionStatus.LOST
            game.completed_at = now
            game.final_score = Decimal("0.00")
        elif not correct:
            game.current_round += 1

        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise GameConflict("A guess has already been submitted for this round") from exc
        refreshed = self.require_game(session_id, guest_id)
        if correct or refreshed.status == SessionStatus.LOST:
            return GuessOutcome(
                correct=correct,
                applied_wrong_guess_penalty=self.normalize_score(penalty, refreshed.rule_set),
                raw_applied_wrong_guess_penalty=penalty,
                result=self.result(refreshed),
            )
        return GuessOutcome(
            correct=False,
            applied_wrong_guess_penalty=self.normalize_score(penalty, refreshed.rule_set),
            raw_applied_wrong_guess_penalty=penalty,
            state=self.state(refreshed),
        )

    def calculate_score(self, game: GameSession) -> Decimal:
        rules = game.rule_set
        wrong_penalties = sum(guess.applied_wrong_guess_penalty for guess in game.guesses if not guess.is_correct)
        time_penalty = Decimal(game.active_guess_ms) / Decimal(1000) * rules.time_penalty_per_second
        hint_penalty = (
            (rules.cryptic_hint_penalty if game.cryptic_hint_used else 0)
            + (rules.title_pattern_penalty if game.title_pattern_used else 0)
        )
        return self.round_score(max(
            rules.minimum_correct_score,
            rules.base_score - wrong_penalties - time_penalty - hint_penalty,
        ), rules)

    def unlock_cryptic(self, session_id: uuid.UUID, guest_id: uuid.UUID) -> HintRead:
        game = self.require_game(session_id, guest_id, lock=True)
        self.ensure_hint_allowed(game)
        newly = not game.cryptic_hint_used
        if newly:
            game.cryptic_hint_used = True
            game.hint_used = True
            game.cryptic_hint_unlocked_at = self.now()
            game.events.append(SessionEvent(event_type="hint_unlocked", round_number=game.current_round))
            self.session.commit()
        return HintRead(
            kind="cryptic", value=game.daily_puzzle.puzzle.cryptic_hint,
            penalty=self.normalize_score(game.rule_set.cryptic_hint_penalty, game.rule_set), newly_unlocked=newly,
        )

    def unlock_title_pattern(self, session_id: uuid.UUID, guest_id: uuid.UUID) -> HintRead:
        game = self.require_game(session_id, guest_id, lock=True)
        self.ensure_hint_allowed(game)
        if not game.cryptic_hint_used:
            raise GameConflict("Unlock the cryptic clue first")
        newly = not game.title_pattern_used
        if newly:
            game.title_pattern_used = True
            game.hint_used = True
            game.title_pattern_unlocked_at = self.now()
            game.events.append(SessionEvent(event_type="hint_unlocked", round_number=game.current_round))
            self.session.commit()
        return HintRead(
            kind="title-pattern", value=title_pattern(game.daily_puzzle.puzzle.movie.title),
            penalty=self.normalize_score(game.rule_set.title_pattern_penalty, game.rule_set), newly_unlocked=newly,
        )

    @staticmethod
    def ensure_hint_allowed(game: GameSession) -> None:
        if game.status != SessionStatus.PLAYING:
            raise GameConflict("Hints cannot be unlocked after the game is complete")
        if game.current_round < 3:
            raise GameConflict("Hints become available in Round 3")

    def result(self, game: GameSession) -> GameResultRead:
        if game.status == SessionStatus.PLAYING:
            raise GameConflict("Results are available only after the game is complete")
        rules = game.rule_set
        event = MessageEvent.FAILED if game.status == SessionStatus.LOST else (
            MessageEvent.SOLVED_EARLY if (game.solved_round or 5) <= 3 else MessageEvent.SOLVED_LATE
        )
        wrong = [guess for guess in game.guesses if not guess.is_correct]
        raw_final_score = game.final_score if game.final_score is not None else Decimal("0.00")
        return GameResultRead(
            status=game.status.value,
            canonical_movie_title=game.daily_puzzle.puzzle.movie.title,
            final_score=self.normalize_score(raw_final_score, rules),
            raw_final_score=raw_final_score,
            raw_score_scale=rules.base_score,
            score_scale=Decimal("50.00"),
            solved_round=game.solved_round,
            wrong_guesses=[GuessResultRead.model_validate({
                "round_number": guess.round_number,
                "submitted_title": guess.submitted_title,
                "response_time_ms": guess.response_time_ms,
                "applied_wrong_guess_penalty": self.normalize_score(guess.applied_wrong_guess_penalty, rules),
                "raw_applied_wrong_guess_penalty": guess.applied_wrong_guess_penalty,
                "hints_used_count": guess.hints_used_count,
            }) for guess in wrong],
            active_guess_ms=game.active_guess_ms,
            cryptic_hint_used=game.cryptic_hint_used,
            title_pattern_used=game.title_pattern_used,
            total_hint_penalty=self.normalize_score(
                (rules.cryptic_hint_penalty if game.cryptic_hint_used else Decimal(0))
                + (rules.title_pattern_penalty if game.title_pattern_used else Decimal(0)),
                rules,
            ),
            time_penalty=self.normalize_score(
                Decimal(game.active_guess_ms) / Decimal(1000) * rules.time_penalty_per_second,
                rules,
            ),
            full_image_url=f"/api/v1/game/{game.id}/image",
            message=self.repository.message(game.daily_puzzle.puzzle_id, event.value),
        )
