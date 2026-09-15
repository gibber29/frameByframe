import uuid
from fastapi import APIRouter,Cookie,HTTPException,Query,Response
from fastapi.responses import FileResponse
from backend.app.api.dependencies import AssetStorageDependency,BadlyGameDependency,GuestTokenDependency
from backend.app.core.config import settings
from backend.app.schemas.badly_game import BoardRead,GuessWrite,HomeRead,RoomCreate,RoomJoin,RoomRead,StateRead
from backend.app.services.badly_game import BadlyConflict,BadlyNotFound

router=APIRouter(prefix='/badly-explained',tags=['badly-explained']);COOKIE='framebyframe_guest'
def identity(token,response,tokens):
    guest=tokens.resolve(token)
    if guest.is_new:response.set_cookie(COOKIE,guest.token,httponly=True,secure=settings.guest_cookie_secure,samesite='lax',max_age=34560000)
    return guest
def fail(e):return HTTPException(status_code=404 if isinstance(e,BadlyNotFound) else 409,detail=str(e))
def room_data(room,guest,service):
    p=service.repository.participant(room.id,guest);return {'code':str(room.code).upper(),'name':room.name,'host_name':room.host_display_name,'status':room.status,'expires_at':room.expires_at,'participant_count':len(room.participants),'joined':bool(p),'current_player_name':p.display_name if p else None,'attempt_id':p.attempt.id if p and p.attempt else None}
@router.get('/home',response_model=HomeRead)
def home(response:Response,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):return service.home(identity(framebyframe_guest,response,tokens).id)
@router.get('/titles',response_model=list[str])
def titles(service:BadlyGameDependency,q:str|None=Query(None,max_length=200)):return service.titles(q)
@router.post('/daily/start',response_model=StateRead)
def daily(response:Response,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    try:return service.state(service.start_daily(identity(framebyframe_guest,response,tokens).id))
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
@router.post('/rooms',response_model=RoomRead,status_code=201)
def create(payload:RoomCreate,response:Response,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    guest=identity(framebyframe_guest,response,tokens)
    try:return room_data(service.create_room(payload.room_name,payload.display_name,guest.id),guest.id,service)
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
@router.get('/rooms/{code}',response_model=RoomRead)
def room(code:str,response:Response,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    guest=identity(framebyframe_guest,response,tokens)
    try:return room_data(service.get_room(code),guest.id,service)
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
@router.post('/rooms/{code}/join',response_model=RoomRead)
def join(code:str,payload:RoomJoin,response:Response,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    guest=identity(framebyframe_guest,response,tokens)
    try:return room_data(service.join_room(code,payload.display_name,guest.id),guest.id,service)
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
@router.post('/rooms/{code}/continue',response_model=StateRead)
def continued(code:str,response:Response,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    guest=identity(framebyframe_guest,response,tokens)
    try:return service.state(service.continue_room(code,guest.id))
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
def owned(id,token,service,tokens):
    guest=tokens.resolve(token)
    if guest.is_new:raise BadlyNotFound('Mystery attempt not found')
    return service.require(id,guest.id)
@router.get('/attempts/{id}',response_model=StateRead)
def state(id:uuid.UUID,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    try:return service.state(owned(id,framebyframe_guest,service,tokens))
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
@router.post('/attempts/{id}/ready',response_model=StateRead)
def ready(id:uuid.UUID,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    try:return service.state(service.ready(id,tokens.resolve(framebyframe_guest).id))
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
@router.post('/attempts/{id}/submit',response_model=StateRead)
def submit(id:uuid.UUID,payload:GuessWrite,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    try:return service.state(service.submit(id,tokens.resolve(framebyframe_guest).id,payload.title))
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
@router.get('/attempts/{id}/image')
def image(id:uuid.UUID,service:BadlyGameDependency,tokens:GuestTokenDependency,storage:AssetStorageDependency,framebyframe_guest:str|None=Cookie(None)):
    try:
        a=owned(id,framebyframe_guest,service,tokens)
        if a.current_round<5 and a.phase!='results':raise BadlyNotFound('Image is locked')
        path=storage.resolve(a.game_set.image_key_snapshot)
    except Exception as e:raise HTTPException(404,'Mystery image not found') from e
    return FileResponse(path,media_type=storage.media_type(path),headers={'Cache-Control':'private, no-store'})
@router.get('/rooms/{code}/leaderboard',response_model=BoardRead)
def board(code:str,service:BadlyGameDependency,tokens:GuestTokenDependency,framebyframe_guest:str|None=Cookie(None)):
    try:
        room=service.get_room(code);guest=tokens.resolve(framebyframe_guest);return {'code':str(room.code).upper(),'room_name':room.name,'entries':service.leaderboard(room,None if guest.is_new else guest.id)}
    except (BadlyConflict,BadlyNotFound) as e:raise fail(e)
