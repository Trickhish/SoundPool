from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from typing import List, Optional
from contextlib import asynccontextmanager
import os
from typing import List
from uuid import uuid4
import json
import asyncio

from configuration import load_config
import deezer as dz
import tracks_manager as tm

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


config = load_config("cs_config.ini")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global config

    if not config["deezer"]["cookie_arl"]:
        raise Exception("cookie_arl must be defined either in the config file or via the DEEZER_COOKIE_ARL variable (.env files will be loaded)")

    print("🟢 CentralServer is up and ready")

    yield

    print("⛔ Shutting down the CentralServer...")

# FastAPI initialization
app = FastAPI(lifespan=lifespan)

# Database setup
DATABASE_URL = "sqlite:///./music_rooms.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()



# Models
class Track(Base):
    __tablename__ = "tracks"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)

    room = relationship("Room", back_populates="tracks", foreign_keys=[room_id])

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=True)
    admin_id = Column(Integer, nullable=False)
    current_track_id = Column(Integer, ForeignKey("tracks.id"), nullable=True)
    votes_to_skip = Column(Integer, default=0)
    is_playing = Column(Boolean, default=False)
    
    tracks = relationship("Track", back_populates="room", foreign_keys=[Track.room_id])
    current_track = relationship("Track", backref="current_room", foreign_keys=[current_track_id])

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    email = Column(String, unique=True, nullable=True)

# Relationships
#Room.tracks = relationship("Track", back_populates="room")
#Track.room = relationship("Room", back_populates="tracks")




# Create tables
Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Schemas
from pydantic import BaseModel

class TrackCreate(BaseModel):
    name: str
    artist: str

class RoomCreate(BaseModel):
    name: str
    password: Optional[str] = None
    admin_id: int


# WebSocket
class PlayerUnit():
    def __init__(self, ws:WebSocket):
        self.ws=ws
        self.id = str(uuid4())
        self.name = None
    
    def sendTest(self):
        rr=tm.search("emmenez moi")
        print(rr[0])

        #song = await asyncio.to_thread(dz.get_song_infos_from_deezer_website, dz.TYPE_TRACK, rr[0]["id"])
        song = dz.get_song_infos_from_deezer_website(dz.TYPE_TRACK, rr[0]["id"])

        #song, url, extension, key = await asyncio.to_thread(tm.getDownloadData, song)
        song, url, extension, key = tm.getDownloadData(song)

        asyncio.run(self.ws.send_text(json.dumps([
            "download", song, url, key
        ])))

        #await websocket.send_text(json.dumps([
        #    "download", song, url, key
        #]))

        print(f"{song['SNG_TITLE']} download data sent")
    
    def play(self):
        return

units: List[PlayerUnit] = []

@app.websocket("/unit")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    thisPlayerUnit = PlayerUnit(websocket)
    units.append(thisPlayerUnit)
    
    try:
        while True:
            r = await websocket.receive_text()
            r = json.loads(r)
            print(r)

            if (r[0]=="id"):
                pun = r[1]
                thisPlayerUnit.name = pun
                print(f"📯🚀 Identified PU_{thisPlayerUnit.id[:4]} as {pun}")

                await asyncio.to_thread(thisPlayerUnit.sendTest)

            #await websocket.send_text(f"Command received: {data}")
    except WebSocketDisconnect:
        units.remove(thisPlayerUnit)
        print(f"🚨 PlayerUnit {thisPlayerUnit.id[:4]} disconnected")

@app.post("/send_command/")
async def send_command(command: str):
    for u in units:
        await u.send_text(command)
    return {"message": "Command sent to all players"}








# Endpoints
@app.get("/")
def none_handler():
    return("SoundPool API is running")

@app.get("/song/{song_id}")
def handle_getsong(song_id: int):
    song = dz.get_song_infos_from_deezer_website(dz.TYPE_TRACK, song_id)
    url,key = tm.getDownloadData(song)

    print(url, key)

    filename = str(song_id)+".mp3"

    r=tm.downloadSong(song, url, key, filename)

    return(FileResponse(path=filename, filename=filename, media_type='text/mp3'))


@app.get("/rooms", response_model=List[str])
def list_public_rooms(db: SessionLocal = Depends(get_db)):
    # Query rooms where the password is None (public rooms)
    public_rooms = db.query(Room).filter(Room.password == None).all()
    
    if not public_rooms:
        raise HTTPException(status_code=404, detail="No public rooms found.")
    
    return [room.name for room in public_rooms]

@app.post("/room/new", response_model=dict)
def create_room(room: RoomCreate, db: SessionLocal = Depends(get_db)):
    existing_room = db.query(Room).filter(Room.name == room.name).first()
    if existing_room:
        raise HTTPException(status_code=400, detail="Room name already exists.")
    
    new_room = Room(name=room.name, password=room.password, admin_id=room.admin_id)
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return {"message": "Room created successfully", "room_id": new_room.id}

@app.post("/room/{room_id}/join")
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

@app.post("/room/{room_id}/leave")
def leave_room(room_id: int, username: str, db: SessionLocal = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.room_id == room_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not in this room.")
    db.delete(user)
    db.commit()
    return {"message": f"{username} left the room."}

@app.post("/room/{room_id}/tracks", response_model=dict)
def add_track_to_room(room_id: int, track: TrackCreate, db: SessionLocal = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found.")
    
    new_track = Track(name=track.name, artist=track.artist, room_id=room_id)
    db.add(new_track)
    db.commit()
    return {"message": "Track added to queue."}

@app.get("/room/{room_id}/tracks", response_model=List[TrackCreate])
def list_tracks_in_room(room_id: int, db: SessionLocal = Depends(get_db)):
    tracks = db.query(Track).filter(Track.room_id == room_id).all()
    return [{"name": t.name, "artist": t.artist} for t in tracks]

@app.get("/tracks/search", response_model=List[TrackCreate])
def search_tracks(query: str, db: SessionLocal = Depends(get_db)):
    tracks = db.query(Track).filter(Track.name.contains(query) | Track.artist.contains(query)).all()
    return [{"name": t.name, "artist": t.artist} for t in tracks]

@app.post("/room/{room_id}/skip")
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

