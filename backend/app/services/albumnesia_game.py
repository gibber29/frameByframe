from __future__ import annotations

import hashlib
import hmac
import logging
import random
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from backend.app.models.entities import (
    AlbumnesiaAttempt, AlbumnesiaDailyProgress, AlbumnesiaGameRound,
    AlbumnesiaGameSet, AlbumnesiaParticipant, AlbumnesiaRoom,
    AlbumnesiaRoundSubmission, ContentEntry,
)
from backend.app.repositories.albumnesia_game import AlbumnesiaGameRepository
from backend.app.repositories.content import normalized_answer

ROUND_SECONDS = 5
FEEDBACK_SECONDS = 1.5
ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DAILY_GAME_VERSION = 2
DISTORTIONS = {"pixel_hangover", "sleeve_shredder", "channel_damage", "identity_crisis", "outline_only"}
logger = logging.getLogger(__name__)


class AlbumnesiaNotFound(Exception):
    pass


class AlbumnesiaConflict(Exception):
    pass


class AlbumnesiaGameService:
    def __init__(self, repository: AlbumnesiaGameRepository, timezone_name: str, secret: str, room_ttl_days: int) -> None:
        self.repository = repository
        self.session = repository.session
        self.timezone = ZoneInfo(timezone_name)
        self.secret = secret.encode()
        self.room_ttl_days = room_ttl_days

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def today(self) -> date:
        return self.now().astimezone(self.timezone).date()

    def _eligible(self) -> list[ContentEntry]:
        eligible = []
        for entry in self.repository.active_albums():
            album = entry.albumnesia
            if not album:
                continue
            methods = set(album.enabled_distortions) & DISTORTIONS
            if not album.subject_mask_regions:
                methods.discard("identity_crisis")
            if methods:
                eligible.append(entry)
        return eligible

    def _snapshot(self, game_set: AlbumnesiaGameSet, entries: list[ContentEntry], rng: random.Random) -> None:
        for number, entry in enumerate(entries, 1):
            album = entry.albumnesia
            methods = sorted(set(album.enabled_distortions) & DISTORTIONS)
            if not album.subject_mask_regions and "identity_crisis" in methods:
                methods.remove("identity_crisis")
            game_set.rounds.append(AlbumnesiaGameRound(
                round_number=number, content_id=entry.id, title_snapshot=entry.primary_answer,
                normalized_answer_snapshot=normalized_answer(entry.primary_answer),
                alternative_answers_snapshot=list(entry.alternative_answers), artist_snapshot=album.artist,
                release_year_snapshot=album.release_year, recognizable_track_snapshot=album.recognizable_track,
                artist_initials_snapshot=album.artist_initials, image_key_snapshot=entry.image_key,
                distortion=rng.choice(methods), distortion_seed=rng.randrange(1, 2_147_483_647),
                text_mask_regions_snapshot=list(album.text_mask_regions),
                subject_mask_regions_snapshot=list(album.subject_mask_regions),
            ))

    def ensure_daily(self) -> AlbumnesiaGameSet:
        day = self.today()
        existing = self.repository.daily_set(day, DAILY_GAME_VERSION)
        if existing:
            return existing
        entries = self._eligible()
        if not entries:
            raise AlbumnesiaConflict("Daily Album needs at least one active, playable album")
        digest = hmac.new(self.secret, f"albumnesia:v{DAILY_GAME_VERSION}:{day.isoformat()}".encode(), hashlib.sha256).digest()
        rng = random.Random(int.from_bytes(digest))
        rng.shuffle(entries)
        game_set = AlbumnesiaGameSet(kind="daily", game_date=day, game_version=DAILY_GAME_VERSION)
        self._snapshot(game_set, entries[:1], rng)
        self.repository.add(game_set)
        try:
            self.repository.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.repository.daily_set(day, DAILY_GAME_VERSION)
            if not existing:
                raise
            return existing
        return self.repository.daily_set(day, DAILY_GAME_VERSION)

    def home(self, guest_id: uuid.UUID) -> dict:
        progress = self.repository.progress(guest_id)
        count = len(self._eligible())
        attempt = None
        daily = self.repository.daily_set(self.today(), DAILY_GAME_VERSION)
        if daily:
            attempt = self.repository.daily_attempt(daily.id, guest_id)
        return {"daily_date": self.today(), "active_album_count": count, "daily_available": count >= 1,
                "streak": progress.current_streak if progress else 0,
                "completed_today": bool(attempt and attempt.status == "completed")}

    def create_room(self, room_name: str, display_name: str, guest_id: uuid.UUID) -> AlbumnesiaRoom:
        entries = self._eligible()
        if len(entries) < 5:
            raise AlbumnesiaConflict("A room needs at least five active, playable albums")
        rng = random.SystemRandom()
        chosen = rng.sample(entries, 5)
        expires = self.now() + timedelta(days=self.room_ttl_days)
        game_set = AlbumnesiaGameSet(kind="room", game_version=DAILY_GAME_VERSION, expires_at=expires)
        self._snapshot(game_set, chosen, rng)
        for _ in range(12):
            code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(7))
            if not self.repository.room(code):
                break
        room = AlbumnesiaRoom(game_set=game_set, code=code, name=room_name,
                              host_display_name=display_name, status="open", expires_at=expires)
        self.repository.add(AlbumnesiaParticipant(room=room, guest_id=guest_id, display_name=display_name))
        self.repository.commit()
        return self.repository.room(code)

    def get_room(self, code: str) -> AlbumnesiaRoom:
        room = self.repository.room(code.strip().upper())
        if not room:
            raise AlbumnesiaNotFound("Room not found or expired")
        if room.expires_at <= self.now() or room.status == "expired":
            if room.status != "expired":
                room.status = "expired"
                self.repository.commit()
            raise AlbumnesiaNotFound("Room not found or expired")
        return room

    def join_room(self, code: str, display_name: str, guest_id: uuid.UUID) -> AlbumnesiaRoom:
        room = self.get_room(code)
        participant = self.repository.participant(room.id, guest_id)
        if not participant:
            if len(room.participants) >= 8:
                raise AlbumnesiaConflict("This room already has eight players")
            participant = AlbumnesiaParticipant(room_id=room.id, guest_id=guest_id, display_name=display_name)
            self.repository.add(participant)
            self.repository.flush()
        else:
            participant.display_name = display_name
        self.repository.commit()
        return self.get_room(code)

    def continue_room(self, code: str, guest_id: uuid.UUID) -> AlbumnesiaAttempt:
        room = self.get_room(code)
        participant = self.repository.participant(room.id, guest_id)
        if not participant:
            raise AlbumnesiaConflict("Join this lobby before continuing to the game")
        attempt = next(iter(participant.attempts), None)
        if not attempt:
            attempt = AlbumnesiaAttempt(
                game_set_id=room.game_set_id, participant=participant,
                guest_id=guest_id, mode="room", score_scale=Decimal("50.00"),
            )
            self.repository.add(attempt)
            try:
                self.repository.commit()
            except IntegrityError as exc:
                self.session.rollback()
                participant = self.repository.participant(room.id, guest_id)
                attempt = next(iter(participant.attempts), None)
                if not attempt:
                    raise AlbumnesiaConflict("Unable to create the room attempt; please retry") from exc
        return self.repository.attempt(attempt.id)

    def start_daily(self, guest_id: uuid.UUID) -> AlbumnesiaAttempt:
        game_set = self.ensure_daily()
        existing = self.repository.daily_attempt(game_set.id, guest_id)
        if existing:
            return existing
        attempt = AlbumnesiaAttempt(game_set_id=game_set.id, guest_id=guest_id, mode="daily", score_scale=Decimal("10.00"))
        self.repository.add(attempt)
        self.repository.commit()
        return self.repository.attempt(attempt.id)

    def require_attempt(self, attempt_id: uuid.UUID, guest_id: uuid.UUID, lock: bool = False) -> AlbumnesiaAttempt:
        attempt = self.repository.attempt(attempt_id, lock)
        if not attempt or attempt.guest_id != guest_id:
            raise AlbumnesiaNotFound("Game attempt not found")
        if attempt.game_set.expires_at and attempt.game_set.expires_at <= self.now() and attempt.status == "playing":
            attempt.status, attempt.phase = "expired", "results"
            self.repository.commit()
            raise AlbumnesiaConflict("This game has expired")
        return attempt

    @staticmethod
    def _round(attempt: AlbumnesiaAttempt) -> AlbumnesiaGameRound:
        return next(row for row in attempt.game_set.rounds if row.round_number == attempt.current_round)

    def _record_timeout(self, attempt: AlbumnesiaAttempt) -> None:
        if any(s.round_number == attempt.current_round for s in attempt.submissions):
            return
        submission = AlbumnesiaRoundSubmission(
            attempt_id=attempt.id, round_number=attempt.current_round, submitted_title=None,
            is_correct=False, remaining_ms=0, answer_time_ms=5000, awarded_score=Decimal("0.00"),
        )
        self.repository.add(submission)
        attempt.submissions.append(submission)
        attempt.total_answer_ms += 5000

    def _complete(self, attempt: AlbumnesiaAttempt, when: datetime) -> None:
        if attempt.status == "completed":
            return
        attempt.status, attempt.phase, attempt.completed_at, attempt.phase_deadline = "completed", "results", when, None
        if attempt.mode == "daily":
            progress = self.repository.progress(attempt.guest_id)
            if not progress:
                # SQL server defaults are unavailable until a flush. Explicit
                # values keep the completion transaction valid and idempotent.
                progress = AlbumnesiaDailyProgress(
                    guest_id=attempt.guest_id, current_streak=0, longest_streak=0,
                )
                self.repository.add(progress)
            day = attempt.game_set.game_date
            if progress.last_completed_date != day:
                if attempt.correct_count > 0:
                    progress.current_streak = progress.current_streak + 1 if progress.last_completed_date == day - timedelta(days=1) else 1
                else:
                    progress.current_streak = 0
                progress.longest_streak = max(progress.longest_streak, progress.current_streak)
                progress.last_completed_date = day
        logger.info("albumnesia_attempt_completed", extra={
            "attempt_id": str(attempt.id), "mode": attempt.mode,
            "correct_count": attempt.correct_count, "score_scale": str(attempt.score_scale),
        })

    def synchronize(self, attempt: AlbumnesiaAttempt) -> AlbumnesiaAttempt:
        now = self.now()
        changed = False
        if attempt.status != "playing":
            return attempt
        if attempt.phase == "memorize" and attempt.phase_deadline and attempt.phase_deadline <= now:
            start = attempt.phase_deadline
            attempt.phase, attempt.phase_started_at = "guess", start
            attempt.phase_deadline = start + timedelta(seconds=ROUND_SECONDS)
            changed = True
        if attempt.phase == "guess" and attempt.phase_deadline and attempt.phase_deadline <= now:
            self._record_timeout(attempt)
            attempt.phase, attempt.phase_started_at = "feedback", now
            attempt.phase_deadline = now + timedelta(seconds=FEEDBACK_SECONDS)
            changed = True
        if attempt.phase == "feedback" and attempt.phase_deadline and attempt.phase_deadline <= now:
            if attempt.current_round == len(attempt.game_set.rounds):
                self._complete(attempt, now)
            else:
                attempt.current_round += 1
                attempt.phase, attempt.phase_started_at, attempt.phase_deadline = "ready", None, None
            changed = True
        if changed:
            self.repository.commit()
            return self.repository.attempt(attempt.id)
        return attempt

    def ready(self, attempt_id: uuid.UUID, guest_id: uuid.UUID) -> AlbumnesiaAttempt:
        attempt = self.synchronize(self.require_attempt(attempt_id, guest_id, lock=True))
        if attempt.phase != "ready" or attempt.status != "playing":
            raise AlbumnesiaConflict("This round has already started")
        now = self.now()
        attempt.phase, attempt.phase_started_at = "memorize", now
        attempt.phase_deadline = now + timedelta(seconds=ROUND_SECONDS)
        self.repository.commit()
        return self.repository.attempt(attempt.id)

    def submit(self, attempt_id: uuid.UUID, guest_id: uuid.UUID, title: str) -> AlbumnesiaAttempt:
        attempt = self.synchronize(self.require_attempt(attempt_id, guest_id, lock=True))
        existing = next((submission for submission in attempt.submissions
                         if submission.round_number == attempt.current_round), None)
        if existing and attempt.phase in {"feedback", "results"}:
            # A retried fifth submission can race the results refresh. Return
            # the authoritative stored outcome rather than inserting twice.
            return attempt
        if attempt.phase != "guess" or not attempt.phase_deadline:
            raise AlbumnesiaConflict("This round is not accepting an answer")
        now = self.now()
        remaining = max(0, min(5000, int((attempt.phase_deadline - now).total_seconds() * 1000)))
        if remaining <= 0:
            return self.synchronize(attempt)
        row = self._round(attempt)
        supplied = normalized_answer(title)
        accepted = {row.normalized_answer_snapshot} | {normalized_answer(value) for value in row.alternative_answers_snapshot}
        correct = bool(supplied) and supplied in accepted
        if correct and attempt.score_scale == Decimal("250.00"):
            # Resume legacy attempts using their original raw scoring rule.
            score = Decimal(remaining) / Decimal(100)
        elif correct:
            score = Decimal("8.00") + Decimal("2.00") * Decimal(remaining) / Decimal("5000")
        else:
            score = Decimal("0.00")
        round_max = Decimal("50.00") if attempt.score_scale == Decimal("250.00") else Decimal("10.00")
        score = max(Decimal("0.00"), min(round_max, score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        answer_ms = 5000 - remaining
        submission = AlbumnesiaRoundSubmission(
            attempt_id=attempt.id, round_number=attempt.current_round, submitted_title=title.strip() or None,
            is_correct=correct, remaining_ms=remaining, answer_time_ms=answer_ms, awarded_score=score,
        )
        self.repository.add(submission)
        attempt.correct_count += int(correct)
        attempt.total_score += score
        attempt.total_answer_ms += answer_ms
        attempt.phase, attempt.phase_started_at = "feedback", now
        attempt.phase_deadline = now + timedelta(seconds=FEEDBACK_SECONDS)
        self.repository.commit()
        return self.repository.attempt(attempt.id)

    def titles(self, query: str | None, limit: int = 30) -> list[str]:
        titles = sorted({entry.primary_answer for entry in self._eligible()}, key=str.casefold)
        if query:
            needle = normalized_answer(query)
            titles = [title for title in titles if needle in normalized_answer(title)]
        return titles[:max(1, min(limit, 100))]

    def state(self, attempt: AlbumnesiaAttempt) -> dict:
        attempt = self.synchronize(attempt)
        now = self.now()
        current = self._round(attempt)
        submission = next((s for s in attempt.submissions if s.round_number == attempt.current_round), None)
        show_cover = attempt.phase in {"ready", "memorize"}
        display_scale = Decimal(len(attempt.game_set.rounds)) * Decimal("10.00")
        legacy = attempt.score_scale != display_scale
        normalize = lambda value: (Decimal(value) * display_scale / attempt.score_scale).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        data = {
            "attempt_id": attempt.id, "mode": attempt.mode,
            "room_code": attempt.participant.room.code if attempt.participant else None,
            "status": attempt.status, "phase": attempt.phase, "round_number": attempt.current_round,
            "total_rounds": len(attempt.game_set.rounds),
            "phase_deadline": attempt.phase_deadline, "server_time": now,
            "image_url": f"/api/v1/albumnesia/attempts/{attempt.id}/image" if show_cover else None,
            "distortion": current.distortion if show_cover else None,
            "distortion_seed": current.distortion_seed if show_cover else None,
            "text_mask_regions": current.text_mask_regions_snapshot if show_cover else None,
            "subject_mask_regions": current.subject_mask_regions_snapshot if show_cover else None,
            "clues": ({"artist_initials": current.artist_initials_snapshot, "release_year": current.release_year_snapshot,
                       "recognizable_track": current.recognizable_track_snapshot} if attempt.phase == "memorize" else None),
            "revealed_title": current.title_snapshot if attempt.phase == "feedback" else None,
            "revealed_artist": current.artist_snapshot if attempt.phase == "feedback" else None,
            "last_correct": submission.is_correct if attempt.phase == "feedback" and submission else None,
            "last_score": normalize(submission.awarded_score) if attempt.phase == "feedback" and submission else None,
            "correct_count": attempt.correct_count, "total_score": normalize(attempt.total_score),
            "max_score": display_scale, "legacy_score": legacy,
            "streak": (self.repository.progress(attempt.guest_id).current_streak if self.repository.progress(attempt.guest_id) else 0),
            "results": None,
        }
        if attempt.phase == "results":
            by_round = {s.round_number: s for s in attempt.submissions}
            data["results"] = [{"round_number": row.round_number, "title": row.title_snapshot, "artist": row.artist_snapshot,
                                "submitted_title": by_round[row.round_number].submitted_title,
                                "correct": by_round[row.round_number].is_correct,
                                "score": normalize(by_round[row.round_number].awarded_score),
                                "answer_time_ms": by_round[row.round_number].answer_time_ms}
                               for row in attempt.game_set.rounds]
        return data

    def leaderboard(self, room: AlbumnesiaRoom, guest_id: uuid.UUID | None = None) -> list[dict]:
        rows = []
        for participant in room.participants:
            attempt = next(iter(participant.attempts), None)
            done = bool(attempt and attempt.status == "completed")
            normalized_score = ((attempt.total_score * Decimal("50.00") / attempt.score_scale)
                                .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if attempt else None
            rows.append({"display_name": participant.display_name, "finished": done,
                         "correct_count": attempt.correct_count if done else None,
                         "score": normalized_score if done else None,
                         "answer_time_ms": attempt.total_answer_ms if done else None,
                         "average_response_ms": round(attempt.total_answer_ms / 5) if done else None,
                         "completed_at": attempt.completed_at if done else None,
                         "is_current": participant.guest_id == guest_id})
        return sorted(rows, key=lambda item: (
            not item["finished"], -(item["correct_count"] or 0), -(item["score"] or 0),
            item["answer_time_ms"] if item["answer_time_ms"] is not None else 10**9,
            item["completed_at"] or datetime.max.replace(tzinfo=timezone.utc),
        ))
