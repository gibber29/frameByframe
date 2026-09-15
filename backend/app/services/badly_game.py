import hashlib, hmac, secrets, string, uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError
from backend.app.models.entities import BadlyAttempt, BadlyDailyProgress, BadlyGameSet, BadlyParticipant, BadlyRoom, BadlySubmission
from backend.app.core.answer_matching import matches_answer, normalized_answer

ROUND_MS=10000; FEEDBACK_MS=1000
class BadlyNotFound(Exception): pass
class BadlyConflict(Exception): pass

class BadlyGameService:
    def __init__(self,repository,timezone_name,secret,room_ttl_days=7): self.repository=repository; self.zone=ZoneInfo(timezone_name); self.secret=secret.encode(); self.room_ttl_days=room_ttl_days
    def now(self): return datetime.now(timezone.utc)
    def today(self): return self.now().astimezone(self.zone).date()
    def eligible(self): return [x for x in self.repository.active() if x.badly_explained and len(x.badly_explained.clues)==4]
    def snapshot(self,entry,kind,day=None): return BadlyGameSet(kind=kind,game_date=day,content_id=entry.id,title_snapshot=entry.primary_answer,normalized_answer_snapshot=normalized_answer(entry.primary_answer),alternative_answers_snapshot=list(entry.alternative_answers),clues_snapshot=list(entry.badly_explained.clues),image_key_snapshot=entry.image_key)
    def ensure_daily(self):
        day=self.today(); found=self.repository.daily(day)
        if found:return found
        items=self.eligible()
        if not items: raise BadlyNotFound('No active Badly Explained mystery is available')
        digest=hmac.new(self.secret,f'badly-explained:{day.isoformat()}'.encode(),hashlib.sha256).digest(); entry=items[int.from_bytes(digest[:8],'big')%len(items)]
        value=self.snapshot(entry,'daily',day); self.repository.add(value)
        try:self.repository.commit()
        except IntegrityError:self.repository.session.rollback()
        return self.repository.daily(day)
    def home(self,guest_id):
        progress=self.repository.progress(guest_id); daily=self.repository.daily(self.today())
        attempt=self.repository.daily_attempt(daily.id,guest_id) if daily else None
        return {'daily_date':self.today(),'active_count':len(self.eligible()),'daily_available':bool(self.eligible()),'streak':progress.current_streak if progress else 0,'completed_today':bool(attempt and attempt.status=='completed')}
    def start_daily(self,guest_id):
        game=self.ensure_daily(); old=self.repository.daily_attempt(game.id,guest_id)
        if old:return old
        value=BadlyAttempt(game_set_id=game.id,guest_id=guest_id,mode='daily');self.repository.add(value);self.repository.commit();return self.repository.attempt(value.id)
    def create_room(self,name,display,guest_id):
        items=self.eligible()
        if not items:raise BadlyNotFound('No active Badly Explained mystery is available')
        game=self.snapshot(secrets.choice(items),'room'); game.expires_at=self.now()+timedelta(days=self.room_ttl_days);self.repository.add(game);self.repository.flush()
        for _ in range(20):
            code=''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(7))
            if not self.repository.room(code):break
        room=BadlyRoom(game_set_id=game.id,code=code,name=name,host_display_name=display,expires_at=game.expires_at);self.repository.add(room);self.repository.flush();self.repository.add(BadlyParticipant(room_id=room.id,guest_id=guest_id,display_name=display));self.repository.commit();return self.repository.room(code)
    def get_room(self,code):
        room=self.repository.room(code.strip().upper())
        if not room:raise BadlyNotFound('Challenge room not found')
        if room.expires_at<=self.now():raise BadlyConflict('This challenge has expired')
        return room
    def join_room(self,code,name,guest_id):
        room=self.get_room(code); participant=self.repository.participant(room.id,guest_id)
        if not participant:self.repository.add(BadlyParticipant(room_id=room.id,guest_id=guest_id,display_name=name));self.repository.commit()
        return self.repository.room(room.code)
    def continue_room(self,code,guest_id):
        room=self.get_room(code); p=self.repository.participant(room.id,guest_id)
        if not p:raise BadlyNotFound('Join this challenge first')
        if p.attempt:return self.repository.attempt(p.attempt.id)
        value=BadlyAttempt(game_set_id=room.game_set_id,participant_id=p.id,guest_id=guest_id,mode='room');self.repository.add(value);self.repository.commit();return self.repository.attempt(value.id)
    def require(self,id,guest,lock=False):
        value=self.repository.attempt(id,lock)
        if not value or value.guest_id!=guest:raise BadlyNotFound('Mystery attempt not found')
        return value
    def complete(self,a,now):
        a.status='completed';a.phase='results';a.completed_at=now;a.phase_deadline=None
        if a.mode=='daily':
            p=self.repository.progress(a.guest_id)
            if not p:p=BadlyDailyProgress(guest_id=a.guest_id,current_streak=0,longest_streak=0);self.repository.add(p)
            day=a.game_set.game_date
            if p.last_completed_date!=day:
                p.current_streak=(p.current_streak+1 if p.last_completed_date==day-timedelta(days=1) else 1) if a.successful_round else 0;p.longest_streak=max(p.longest_streak,p.current_streak);p.last_completed_date=day
    def timeout(self,a):
        if not any(x.round_number==a.current_round for x in a.submissions):
            row=BadlySubmission(attempt_id=a.id,round_number=a.current_round,submitted_title=None,is_correct=False,remaining_ms=0);self.repository.add(row);a.submissions.append(row)
    def sync(self,a):
        now=self.now()
        if a.status!='playing':return a
        if a.phase=='active' and a.phase_deadline<=now:self.timeout(a);a.phase='feedback';a.phase_deadline=now+timedelta(milliseconds=FEEDBACK_MS);self.repository.commit();return self.repository.attempt(a.id)
        if a.phase=='feedback' and a.phase_deadline<=now:
            if a.current_round==5:self.complete(a,now)
            else:a.current_round+=1;a.phase='ready';a.phase_deadline=None
            self.repository.commit();return self.repository.attempt(a.id)
        return a
    def ready(self,id,guest):
        a=self.sync(self.require(id,guest,True))
        if a.phase!='ready':raise BadlyConflict('This round has already started')
        a.phase='active';a.phase_deadline=self.now()+timedelta(milliseconds=ROUND_MS);self.repository.commit();return self.repository.attempt(a.id)
    def submit(self,id,guest,title):
        a=self.sync(self.require(id,guest,True)); old=next((x for x in a.submissions if x.round_number==a.current_round),None)
        if old:return a
        if a.phase!='active':raise BadlyConflict('This round is not accepting an answer')
        remaining=max(0,min(ROUND_MS,int((a.phase_deadline-self.now()).total_seconds()*1000)))
        if remaining<=0:return self.sync(a)
        correct=matches_answer(title,a.game_set.title_snapshot,a.game_set.alternative_answers_snapshot)
        row=BadlySubmission(attempt_id=a.id,round_number=a.current_round,submitted_title=title.strip() or None,is_correct=correct,remaining_ms=remaining);self.repository.add(row);a.submissions.append(row)
        if correct:a.successful_round=a.current_round;a.successful_remaining_ms=remaining;self.complete(a,self.now())
        else:a.phase='feedback';a.phase_deadline=self.now()+timedelta(milliseconds=FEEDBACK_MS)
        self.repository.commit();return self.repository.attempt(a.id)
    def titles(self,q=None):
        values=sorted({x.primary_answer for x in self.eligible()},key=str.casefold)
        if not q:return values
        needle=normalized_answer(q);return sorted([x for x in values if needle in normalized_answer(x)],key=lambda x:(not normalized_answer(x).startswith(needle),x.casefold()))[:30]
    def state(self,a):
        a=self.sync(a); previous=a.game_set.clues_snapshot[:min(a.current_round-1,4)]; current=a.game_set.clues_snapshot[a.current_round-1] if a.current_round<=4 else None; sub=next((x for x in a.submissions if x.round_number==a.current_round),None);p=self.repository.progress(a.guest_id)
        return {'attempt_id':a.id,'mode':a.mode,'room_code':a.participant.room.code if a.participant else None,'lobby_name':a.participant.room.name if a.participant else None,'status':a.status,'phase':a.phase,'round_number':a.current_round,'deadline':a.phase_deadline,'server_time':self.now(),'current_hint':current if a.phase in ('active','feedback') else None,'previous_hints':previous,'image_url':f'/api/v1/badly-explained/attempts/{a.id}/image' if a.current_round==5 and a.phase in ('ready','active') else None,'last_correct':sub.is_correct if sub and a.phase=='feedback' else None,'streak':p.current_streak if p else 0,'result':self.result(a) if a.phase=='results' else None}
    def result(self,a):
        return {'title':a.game_set.title_snapshot,'image_url':f'/api/v1/badly-explained/attempts/{a.id}/image','successful_round':a.successful_round,'remaining_ms':a.successful_remaining_ms or 0,'rank_value':6-a.successful_round if a.successful_round else 0,'daily_number':(a.game_set.game_date-date(2026,1,1)).days+1 if a.game_set.game_date else None,'completed_at':a.completed_at}
    def leaderboard(self,room,current):
        attempts={x.participant_id:x for x in self.repository.room_attempts(room.game_set_id)}; rows=[]
        for p in room.participants:
            a=attempts.get(p.id);done=bool(a and a.status=='completed');rows.append({'display_name':p.display_name,'finished':done,'successful_round':a.successful_round if done else None,'remaining_ms':a.successful_remaining_ms if done else None,'completed_at':a.completed_at if done else None,'is_current':p.guest_id==current})
        return sorted(rows,key=lambda x:(not x['finished'],x['successful_round'] is None,x['successful_round'] or 99,-(x['remaining_ms'] or 0),x['completed_at'] or datetime.max.replace(tzinfo=timezone.utc)))
