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