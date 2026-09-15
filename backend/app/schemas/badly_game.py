import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator

class NameBase(BaseModel):
    @staticmethod
    def clean(value):
        value=value.strip()
        if len(value)<2 or any(x in value for x in '<>'): raise ValueError('must contain at least two supported characters')
        return value
class RoomCreate(NameBase):
    room_name:str=Field(min_length=2,max_length=80);display_name:str=Field(min_length=2,max_length=40)
    _clean=field_validator('room_name','display_name')(NameBase.clean)
class RoomJoin(NameBase):
    display_name:str=Field(min_length=2,max_length=40)
    _clean=field_validator('display_name')(NameBase.clean)
class GuessWrite(BaseModel): title:str=Field(default='',max_length=300)
class HomeRead(BaseModel): daily_date:date;active_count:int;daily_available:bool;streak:int;completed_today:bool
class RoomRead(BaseModel): code:str;name:str;host_name:str;status:str;expires_at:datetime;participant_count:int;joined:bool;current_player_name:str|None=None;attempt_id:uuid.UUID|None=None
class ResultRead(BaseModel): title:str;image_url:str;successful_round:int|None;remaining_ms:int;rank_value:int;daily_number:int|None;completed_at:datetime
class StateRead(BaseModel):
    attempt_id:uuid.UUID;mode:str;room_code:str|None=None;lobby_name:str|None=None;status:str;phase:str;round_number:int;deadline:datetime|None;server_time:datetime;current_hint:str|None=None;previous_hints:list[str];image_url:str|None=None;last_correct:bool|None=None;streak:int;result:ResultRead|None=None
class LeaderRead(BaseModel): display_name:str;finished:bool;successful_round:int|None=None;remaining_ms:int|None=None;completed_at:datetime|None=None;is_current:bool=False
class BoardRead(BaseModel): code:str;room_name:str;entries:list[LeaderRead]
