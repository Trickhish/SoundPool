import argparse
from datetime import datetime, timedelta
from enum import Enum
import io
from math import floor
import sys
import requests

import uvicorn
import Colors
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

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
from configuration import ConfigError, config
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

MAX_LINE_LENGTH = 60

@asynccontextmanager
async def lifespan(app: FastAPI):
    #global config

    #config=load_config("cs_config.ini")

    if not config["deezer"]["cookie_arl"]:
        raise ConfigError("cookie_arl must be defined either in the config file or via the SP_DEEZER_ARL variable (.env files will be loaded)")

    if config["server"]["debug"]=="true":
        print(f"⚙️ {Colors.BLUE}CONFIG: {Colors.NONE}")
        pref = f"{Colors.BLUE}║{Colors.NONE} "

        pll = MAX_LINE_LENGTH+16
        print(f"{Colors.BLUE}╔{'═'*pll}{Colors.NONE}")
        for k in ["server","database","deezer"]:
            print(pref, end="")
            print(f" {Colors.LIGHT_RED}[{k.upper()}]:{Colors.NONE}")
            for chk,chv in config[k].items():
                print(pref, end="")
                print(f"   {chk}: {chv[:MAX_LINE_LENGTH]}")
                for i in range(1, floor(len(chv)/(MAX_LINE_LENGTH+1))+1):
                    print(pref, end="")
                    print(f"   {" "*(len(chk)+2)}{chv[(MAX_LINE_LENGTH*i):(MAX_LINE_LENGTH*(i+1))]}")
            print(pref)
        print(f"{Colors.BLUE}╚{'═'*pll}{Colors.NONE}")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    print("🟢 CentralServer is up and ready\n")

    yield

    print("⛔ Shutting down the CentralServer...\n")



class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        mtcl = {"GET": Colors.NONE, "POST":Colors.MAGENTA, "PUT":Colors.LIGHT_GREEN, "OPTIONS":Colors.LIGHT_CYAN}
        print(f"{mtcl[request.method] if request.method in mtcl.keys() else Colors.NONE}[{request.method}]{Colors.NONE}", end='')
        
        host = str(request.base_url)
        if ("://" in host):
            host=host.split("://")[1]
        host=host.split("/")[0]
        endpoint=str(request.url).split(host)[1]

        host=host.split(":")[0]

        print(f" {host} : {endpoint} ->", end='')

        #print(f"Request: {request.method} {request.url}")
        #print(f"Headers: {request.headers}")
        
        response = await call_next(request)

        rpc=Colors.NONE
        if response.status_code<300: # GOOD
            rpc=Colors.GREEN
        elif response.status_code<400: # REDIRECTION
            rpc=Colors.LIGHT_BLACK
        elif response.status_code<500: # BAD
            rpc=Colors.LIGHT_RED
        else: # SERVER ERROR
            rpc=Colors.RED
        print(f" {rpc}{response.status_code}{Colors.NONE}")

        try:
            if isinstance(response, StreamingResponse):
                buffer = io.BytesIO()
                async for chunk in response.body_iterator:
                    buffer.write(chunk)
                body = buffer.getvalue()

                print(f" Stream: {body}")
            else:
                body = await response.body()
                try:
                    response_json = json.loads(body.decode())
                    print(f" Response body: {json.dumps(response_json, indent=2)}")
                except json.JSONDecodeError:
                    print(f" Response body (non-JSON): {body.decode()}")
        except Exception as e:
            print(f" Error when trying to get response body: {str(e)}")
        
        #print(f"Response status: {response.status_code}")
        
        return response


# FastAPI initialization
app = FastAPI(lifespan=lifespan)

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(room_router, prefix="/room", tags=["Rooms"])

if (config and config["server"]["debug"]=="true"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins (any host)
        allow_credentials=True,
        allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
        allow_headers=["*"],  # Allows all headers
    )
    app.add_middleware(RequestLoggerMiddleware)

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


if (__name__=="__main__"):
    host = config["server"]["host"]
    port = int(config["server"]["port"])
    dbg = (config["server"]["debug"].lower().strip()=="true")
    wdir = os.path.dirname(os.path.realpath(__file__))
    workersnb = int(config["server"]["workers"]) if not dbg else 1

    if (len(sys.argv)>=2 and sys.argv[1] in ["-c", "--config"]):
        if (not os.path.exists("install.py")):
            r = requests.get("https://github.com/Trickhish/SoundPool/raw/refs/heads/main/central_server/install.py")
            with open("install.py", mode="wb") as file:
                file.write(r.content)
        import install
        install.main()

    print(f"🚀 Starting the SoundPool server on {Colors.CYAN}http://{host}:{port}{Colors.NONE}.\n")
    if (dbg):
        print(f"⚠️ {Colors.YELLOW}Warning{Colors.NONE}, DEBUG mode is activated. \n{Colors.LIGHT_RED}Do not use this mode for production!{Colors.NONE}")
        pll = MAX_LINE_LENGTH+16
        print(f"{Colors.YELLOW}╔{'═'*pll}{Colors.NONE}")

        for ll in [
            f"The number of workers was reduced to {Colors.LIGHT_RED}{workersnb}{Colors.NONE}",
            f"The CORS wildcard is activated.",
            f"The DEBUG middleware is activated.",
            f"The server will reload on changes in {Colors.UNDERLINE}{wdir}{Colors.NONE}"
        ]:
            if (len(ll) > MAX_LINE_LENGTH):
                print(f"{Colors.YELLOW}║{Colors.NONE} ", end="")

                print(ll[:MAX_LINE_LENGTH])
                lcl=Colors.lastUsed(ll[:MAX_LINE_LENGTH])
                for i in range(1, floor(len(ll)/(MAX_LINE_LENGTH+1))+1):
                    print(f"{Colors.NONE}{Colors.YELLOW}║{Colors.NONE} ", end="")
                    print((" "*5)+lcl+ll[(MAX_LINE_LENGTH*i):(MAX_LINE_LENGTH*(i+1))]+Colors.NONE)
                    lcl=Colors.lastUsed(ll[(MAX_LINE_LENGTH*i):(MAX_LINE_LENGTH*(i+1))])
            else:
                print(f"{Colors.YELLOW}║{Colors.NONE} {ll}")
        
        print(f"{Colors.YELLOW}╚{'═'*pll}{Colors.NONE}\n")
    else:
        if (workersnb<3):
            print(f"⚠️ {Colors.YELLOW}Warning{Colors.NONE}, for a production environment, {workersnb} workers might not be enough.")
        else:
            print(f"⛏️ Running {workersnb} workers")
    print("")

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=dbg,
        workers=workersnb,
        log_level="warning",
        access_log=dbg
    )