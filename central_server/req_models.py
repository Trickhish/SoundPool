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
    admin_id: int

class QueueAddRequest(BaseModel):
    song_id: str
    title: str
    artist: str
    img_url: str = ""

class SeekRequest(BaseModel):
    percent: float