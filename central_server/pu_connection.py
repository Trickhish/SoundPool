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
import sse

router = APIRouter()

db = SessionLocal()

class PlayerUnit():
    def __init__(self, ws:WebSocket):
        self.ws=ws
        self.id = None
        self.name = None
        self.ownerMail = None
        self.ownerId = None
        self.owner = None
    
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
            owm = r[3]
            self.ownerMail = owm
            self.name = pun

            pu:Unit = db.query(Unit).filter(
                Unit.id == piud
            ).first()

            if not pu:
                print(f"{pun} used an unregistered id")
                await self.send(["error", "unknown_id"])
                return
            
            self.id = piud
            pu.online=True
            pu.name=pun

            await sse.triggerEvent(f"pu_{piud}", {"type":"status", "id":pu.id, "status":pu.status, "name":pu.name})
            
            if (owm):
                pu.owner_mail = owm

                owner:User = db.query(User).filter(
                    User.email == owm
                ).first()

                if owner!=None:
                    self.ownerId=owner.id
                    self.owner=owner
                    pu.owner_id = owner.id

                    #scl = sse.getSseClients(owner.id)
                    #for sc in scl:
                    #    if sc!=None:
                    #        await sc.trigger("mypu", {"type": "status", "id": pu.id, "status": True, "name": pu.name})
                    await sse.clientsTrigger(owner.id, "mypu", {"type": "status", "id": pu.id, "status": pu.status, "name": pu.name})

            db.commit()
            db.refresh(pu)
           
            print(f"🚀 PU_{self.id[:4]} is online ({pun})")
        elif r[0]=='ask_id':
            self.id = str(uuid4())
            pun = r[1]
            owm = r[2]
            self.ownerMail = owm
            self.name = pun
            print(f"📯 New player unit PU_{self.id[:4]} ({pun})")

            npu = Unit(id=self.id, name=pun, online=True, status="idle")

            #await self.ws.send_text(json.dumps(["id_assign", self.id]))
            await self.send(["id_assign", self.id])

            await sse.triggerEvent(f"pu_{self.id}", {"type":"status", "id":self.id, "status":pu.status, "name":self.name})

            if (owm):
                owner:User = db.query(User).filter(
                    User.email == owm
                ).first()

                if owner!=None:
                    self.ownerId=owner.id
                    self.owner=owner
                    npu.owner_id = owner.id

                    #scl = sse.getSseClients(owner.id)
                    #for sc in scl:
                    #    if sc!=None:
                    #        await sc.trigger("mypu", {"type": "status", "id": pu.id, "status": True, "name": pu.name})
                    await sse.clientsTrigger(owner.id, "mypu", {"type": "status", "id": pu.id, "status": True, "name": pu.name})
            db.add(npu)
            db.commit()
            db.refresh(npu)
            #await asyncio.to_thread(self.sendTest)
        
        elif r[0]=="status":
            [_,sts] = r

            unit:Unit = db.query(Unit).filter(Unit.id==self.id).first()
            unit.status=sts
            db.commit()
            db.refresh(unit)

            await sse.triggerEvent(f"pu_{self.id}", {"type":"status", "id":self.id, "status":sts, "name":self.name})

        elif r[0]=="playing":
            [_,mid,mn,mdur,img_url] = r
            
            await sse.triggerEvent(f"pu_{self.id}", {"type":"playing_song", "id":mid, "name":mn, "duration":mdur, "img_url":img_url})

        elif r[0]=="progress":
            [_,sname, sid, pos, dur, img_url] = r
            
            await sse.triggerEvent(f"pu_{self.id}", {"type":"progress", "progress":pos, "duration":dur, "name":sname, "id":sid, "img_url":img_url})

        #await websocket.send_text(f"Command received: {data}")

    async def send(self, dt):
        await self.ws.send_text(json.dumps(dt))

    async def play(self):
        await self.send(["control", "play"])
    async def pause(self):
        await self.send(["control", "pause"])

units: List[PlayerUnit] = []


def getUnitById(uid):
    for u in units:
        if u.id == uid:
            return(u)
    return(None)


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

        await sse.triggerEvent(f"pu_{thisPlayerUnit.id}", {"type":"status", "id":thisPlayerUnit.id, "status":"offline", "name":thisPlayerUnit.name})

        if (thisPlayerUnit.owner):
            #scl = sse.getSseClients(thisPlayerUnit.owner.id)
            #for sc in scl:
            #    if sc!=None:
            #        await sc.trigger("mypu", {"type": "status", "id": thisPlayerUnit.id, "status": False, "name": thisPlayerUnit.name})
            await sse.clientsTrigger(thisPlayerUnit.owner, "mypu", {"type": "status", "id": thisPlayerUnit.id, "status":"offline", "name": thisPlayerUnit.name})
        if (thisPlayerUnit.id != None):
            unit:Unit = db.query(Unit).filter(
                Unit.id==thisPlayerUnit.id
            ).first()
            if (unit!=None):
                unit.online=False
                db.commit()
                db.refresh(unit)
            print(f"🚨 PlayerUnit {thisPlayerUnit.id[:4]} disconnected")
        else:
            print(f"🚨 unregistered PlayerUnit ({thisPlayerUnit.name}) disconnected")

@router.post("/send_command/")
async def send_command(command: str):
    for u in units:
        await u.send_text(command)
    return {"message": "Command sent to all players"}