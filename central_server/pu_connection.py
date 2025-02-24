import json
from typing import List
from uuid import uuid4
from fastapi import WebSocket, WebSocketDisconnect, APIRouter, HTTPException, Depends
import bcrypt
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import JSONResponse
import traceback

import deezer as dz
import tracks_manager as tm

from db_models import *
from req_models import *
from database import *

from configuration import config

router = APIRouter()

db = SessionLocal()

class PlayerUnit():
    def __init__(self, ws:WebSocket):
        self.ws=ws
        self.id = None
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
    
    async def received(self, msg):
        r = json.loads(msg)
        print(r)

        if (r[0]=="id"):
            pun = r[2]
            piud = r[1]
            self.name = pun

            pu = db.query(Unit).filter(
                Unit.id == piud
            ).first()

            if not pu:
                print(f"{pun} used an unregistered id")
                await self.send(["error", "unknown_id"])
                return

            self.id = piud
            print(f"🚀 PU_{self.id[:4]} is online ({pun})")
        elif r[0]=='ask_id':
            self.id = str(uuid4())
            pun = r[1]
            self.name = pun
            print(f"📯 New player unit PU_{self.id[:4]} ({pun})")

            #await self.ws.send_text(json.dumps(["id_assign", self.id]))
            await self.send(["id_assign", self.id])

            #await asyncio.to_thread(self.sendTest)

        #await websocket.send_text(f"Command received: {data}")

    async def send(self, dt):
        await self.ws.send_text(json.dumps(dt))

    def play(self):
        return

units: List[PlayerUnit] = []



@router.websocket("")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    thisPlayerUnit = PlayerUnit(websocket)
    units.append(thisPlayerUnit)
    
    try:
        while True:
            r = await websocket.receive_text()
            await thisPlayerUnit.received(r)
            
    except WebSocketDisconnect:
        units.remove(thisPlayerUnit)
        print(f"🚨 PlayerUnit {thisPlayerUnit.id[:4]} disconnected")

@router.post("/send_command/")
async def send_command(command: str):
    for u in units:
        await u.send_text(command)
    return {"message": "Command sent to all players"}