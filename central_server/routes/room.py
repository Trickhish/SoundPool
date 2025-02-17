import bcrypt
from fastapi import APIRouter, HTTPException, Depends
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import *
from req_models import *
from database import *

router = APIRouter()


@router.post("/room/new", response_model=dict)
def create_room(room: RoomCreate, db: SessionLocal = Depends(get_db)):
    existing_room = db.query(Room).filter(Room.name == room.name).first()
    if existing_room:
        raise HTTPException(status_code=400, detail="Room name already exists.")
    
    new_room = Room(name=room.name, password=room.password, admin_id=room.admin_id)
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return {"message": "Room created successfully", "room_id": new_room.id}

@router.post("/room/{room_id}/join")
def join_room(room_id: int, username: str, password: Optional[str] = None, db: SessionLocal = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    if room.password and room.password != password:
        raise HTTPException(status_code=403, detail="Incorrect password.")
    
    user = User(username=username, room_id=room_id)
    db.add(user)
    db.commit()
    return {"message": f"{username} joined room {room.name}"}

@router.post("/room/{room_id}/leave")
def leave_room(room_id: int, username: str, db: SessionLocal = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.room_id == room_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not in this room.")
    db.delete(user)
    db.commit()
    return {"message": f"{username} left the room."}

@router.post("/room/{room_id}/tracks", response_model=dict)
def add_track_to_room(room_id: int, track: TrackCreate, db: SessionLocal = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    
    new_track = Track(name=track.name, artist=track.artist, room_id=room_id)
    db.add(new_track)
    db.commit()
    return {"message": "Track added to queue."}

@router.get("/room/{room_id}/tracks", response_model=List[TrackCreate])
def list_tracks_in_room(room_id: int, db: SessionLocal = Depends(get_db)):
    tracks = db.query(Track).filter(Track.room_id == room_id).all()
    return [{"name": t.name, "artist": t.artist} for t in tracks]

@router.post("/room/{room_id}/skip")
def vote_to_skip(room_id: int, username: str, is_admin: bool = False, db: SessionLocal = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    
    current_track = db.query(Track).filter(Track.id == room.current_track).first()
    if not current_track:
        raise HTTPException(status_code=404, detail="No track is currently playing.")
    
    if is_admin:
        db.delete(current_track)
        db.commit()
        return {"message": "Track skipped by admin."}
    
    current_track.votes_to_skip += 1
    db.commit()
    
    if current_track.votes_to_skip >= 3:  # Example threshold for skipping
        db.delete(current_track)
        db.commit()
        return {"message": "Track skipped by votes."}
    
    return {"message": f"Vote to skip recorded. Current votes: {current_track.votes_to_skip}"}

