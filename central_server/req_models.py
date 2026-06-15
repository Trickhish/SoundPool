from typing import Optional
from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    token: str
    token_type: str

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str

class TrackCreate(BaseModel):
    name: str
    artist: str

class RoomCreate(BaseModel):
    name: str
    password: Optional[str] = None

class RoomJoinRequest(BaseModel):
    password: Optional[str] = None

class RoomRightsRequest(BaseModel):
    user_id: int
    is_admin: Optional[bool] = None
    can_add: Optional[bool] = None
    can_remove: Optional[bool] = None
    can_reorder: Optional[bool] = None
    can_playpause: Optional[bool] = None
    can_skip: Optional[bool] = None
    can_vote_skip: Optional[bool] = None
    can_seek: Optional[bool] = None

class QueueAddRequest(BaseModel):
    song_id: str
    title: str
    artist: str
    img_url: str = ""

class SeekRequest(BaseModel):
    percent: float

class VolumeRequest(BaseModel):
    level: float

class ShuffleRequest(BaseModel):
    on: bool

class RepeatRequest(BaseModel):
    mode: str

class QueueMoveRequest(BaseModel):
    frm: int
    to: int

class QueueIndexRequest(BaseModel):
    index: int

class FavoriteRequest(BaseModel):
    song_id: str
    title: str = ""
    artist: str = ""
    img_url: str = ""