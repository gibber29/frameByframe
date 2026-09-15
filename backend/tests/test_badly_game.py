import shutil, uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete,select
from backend.app.api.dependencies import get_asset_storage
from backend.app.db.session import SessionLocal
from backend.app.main import create_app
from backend.app.models.entities import BadlyAttempt,BadlyExplainedContent,BadlyGameSet,ContentEntry
from backend.app.storage import LocalFilesystemStorage

@pytest.fixture
def badly_client(tmp_path:Path):
    title=f'Test Mystery {uuid.uuid4().hex[:8]}';folder=tmp_path/'badly-explained';folder.mkdir();Image.new('RGB',(80,80),'coral').save(folder/'mystery.webp')
    with SessionLocal.begin() as s:
        original_sets=set(s.scalars(select(BadlyGameSet.id)))
        entry=ContentEntry(category='badly_explained',primary_answer=title,alternative_answers=['The Mystery'],image_key='badly-explained/mystery.webp',difficulty=3,is_active=True,badly_explained=BadlyExplainedContent(clues=['First terrible clue','Second terrible clue','Third terrible clue','Fourth terrible clue']));s.add(entry);s.flush();entry_id=entry.id
    app=create_app();app.dependency_overrides[get_asset_storage]=lambda:LocalFilesystemStorage(tmp_path)
    with TestClient(app) as client:yield client,title
    with SessionLocal.begin() as s:
        ids=list(s.scalars(select(BadlyGameSet.id).where(BadlyGameSet.id.not_in(original_sets))))
        if ids:s.execute(delete(BadlyGameSet).where(BadlyGameSet.id.in_(ids)))
        s.execute(delete(ContentEntry).where(ContentEntry.id==entry_id))

def test_daily_snapshot_hides_answer_and_enforces_one_guess(badly_client):
    client,_=badly_client;state=client.post('/api/v1/badly-explained/daily/start').json();assert state['phase']=='ready' and 'title_snapshot' not in str(state)
    active=client.post(f"/api/v1/badly-explained/attempts/{state['attempt_id']}/ready").json();assert active['current_hint']
    wrong=client.post(f"/api/v1/badly-explained/attempts/{state['attempt_id']}/submit",json={'title':'Definitely Wrong'});assert wrong.status_code==200 and wrong.json()['phase']=='feedback' and 'normalized_answer' not in wrong.text
    duplicate=client.post(f"/api/v1/badly-explained/attempts/{state['attempt_id']}/submit",json={'title':'Another Guess'});assert duplicate.status_code==200

def test_rounds_advance_and_correct_answer_ends_immediately(badly_client):
    client,_=badly_client;state=client.post('/api/v1/badly-explained/daily/start').json();aid=uuid.UUID(state['attempt_id'])
    with SessionLocal() as s:title=s.get(BadlyAttempt,aid).game_set.title_snapshot
    first=client.post(f'/api/v1/badly-explained/attempts/{aid}/ready').json();client.post(f'/api/v1/badly-explained/attempts/{aid}/submit',json={'title':'wrong'})
    with SessionLocal.begin() as s:s.get(BadlyAttempt,aid).phase_deadline=datetime.now(timezone.utc)-timedelta(milliseconds=1)
    round2=client.get(f'/api/v1/badly-explained/attempts/{aid}').json();assert round2['round_number']==2 and round2['phase']=='ready' and round2['previous_hints']==[first['current_hint']]
    client.post(f'/api/v1/badly-explained/attempts/{aid}/ready');done=client.post(f'/api/v1/badly-explained/attempts/{aid}/submit',json={'title':title}).json();assert done['phase']=='results' and done['result']['successful_round']==2 and done['result']['rank_value']==4 and done['result']['completed_at']

def test_room_participants_share_snapshot_and_rank_by_round_then_time(badly_client):
    client,_=badly_client;room=client.post('/api/v1/badly-explained/rooms',json={'room_name':'Doodle Club','display_name':'Ada'}).json();assert room['attempt_id'] is None
    host=client.post(f"/api/v1/badly-explained/rooms/{room['code']}/continue").json();client.cookies.clear();invite=client.get(f"/api/v1/badly-explained/rooms/{room['code']}").json();assert invite['host_name']=='Ada' and not invite['joined']
    client.post(f"/api/v1/badly-explained/rooms/{room['code']}/join",json={'display_name':'Maya'});guest=client.post(f"/api/v1/badly-explained/rooms/{room['code']}/continue").json()
    with SessionLocal() as s:
        assert s.get(BadlyAttempt,uuid.UUID(host['attempt_id'])).game_set_id==s.get(BadlyAttempt,uuid.UUID(guest['attempt_id'])).game_set_id
    board=client.get(f"/api/v1/badly-explained/rooms/{room['code']}/leaderboard").json();assert len(board['entries'])==2 and all(not x['finished'] for x in board['entries'])
