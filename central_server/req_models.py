from typing import Optional, List
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

class PartyJoinRequest(BaseModel):
    username: str

class RoomRightsRequest(BaseModel):
    user_id: int
    # Optional role preset to stamp first (owner is not assignable via this API).
    role: Optional[str] = None
    is_admin: Optional[bool] = None
    can_add: Optional[bool] = None
    can_remove: Optional[bool] = None
    can_reorder: Optional[bool] = None
    can_playpause: Optional[bool] = None
    can_skip: Optional[bool] = None
    can_vote_skip: Optional[bool] = None
    can_vote: Optional[bool] = None
    can_seek: Optional[bool] = None
    can_change_volume: Optional[bool] = None
    can_manage_speakers: Optional[bool] = None
    can_manage_party: Optional[bool] = None

class QueueAddRequest(BaseModel):
    song_id: str
    title: str
    artist: str
    img_url: str = ""
    at_next: bool = False   # insert right after the current track ("play next")

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

class QueueVoteRequest(BaseModel):
    uid: int             # stable id of the queue track (survives reordering)
    direction: int       # +1 upvote, -1 downvote, 0 clear my vote

class DisplayPairRequest(BaseModel):
    code: str

class DisplayModeRequest(BaseModel):
    mode: str

class DisplayConfigRequest(BaseModel):
    show_player: Optional[bool] = None
    show_lyrics: Optional[bool] = None
    show_queue: Optional[bool] = None
    show_skipvotes: Optional[bool] = None
    show_activity: Optional[bool] = None
    show_members: Optional[bool] = None
    lyrics_full: Optional[bool] = None
    animate_bg: Optional[bool] = None
    mascot: Optional[bool] = None
    show_qr: Optional[bool] = None
    show_message: Optional[bool] = None
    message: Optional[str] = None

class OutputRequest(BaseModel):
    unit_id: str

class UnitOutputsRequest(BaseModel):
    sinks: List[str] = []

class SinkVolumeRequest(BaseModel):
    sink: str
    level: float

class UnitTestRequest(BaseModel):
    sink: Optional[str] = None

class UnitRenameRequest(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None

class BtRequest(BaseModel):
    mac: Optional[str] = None
    seconds: Optional[int] = None

class FavoriteRequest(BaseModel):
    song_id: str
    title: str = ""
    artist: str = ""
    img_url: str = ""
    room_id: Optional[int] = None   # for a heads-up on the big-screen activity feed