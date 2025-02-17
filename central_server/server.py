from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from typing import List, Optional
from contextlib import asynccontextmanager
import os
from typing import List
from uuid import uuid4
import json
import asyncio
import jwt
import bcrypt

#from configuration import load_config
from configuration import config
import deezer as dz
import tracks_manager as tm

from db_models import *
from req_models import *
from database import *
from routes.auth import *

from routes.auth import router as auth_router
from routes.room import router as room_router

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



#config = load_config("cs_config.ini")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global config

    if not config["deezer"]["cookie_arl"]:
        raise Exception("cookie_arl must be defined either in the config file or via the DEEZER_COOKIE_ARL variable (.env files will be loaded)")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    print("🟢 CentralServer is up and ready")

    yield

    print("⛔ Shutting down the CentralServer...")


# FastAPI initialization
app = FastAPI(lifespan=lifespan)

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(room_router, prefix="/room", tags=["Rooms"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (any host)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)



# Endpoints
@app.get("/")
def none_handler():
    return("SoundPool API is running")


# tkr: str = Depends(verify_token)

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


@app.get("/tracks/search", response_model=List[TrackCreate])
def search_tracks(query: str, db: SessionLocal = Depends(get_db)):
    tracks = db.query(Track).filter(Track.name.contains(query) | Track.artist.contains(query)).all()
    return [{"name": t.name, "artist": t.artist} for t in tracks]

