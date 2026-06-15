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
        self.state = None   # latest authoritative snapshot reported by the unit
        self._last_np_id = None  # last song id logged to history
        self.audio = None   # latest audio-device state (sinks/outputs/bluetooth)
    
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

            # Close and evict any stale connections for the same unit
            for stale in [u for u in units if u is not self and u.id == piud]:
                try:
                    await stale.ws.close()
                except Exception:
                    pass
                units.remove(stale)

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

        elif r[0]=="state":
            # Full authoritative snapshot from the unit. Cache it (so fresh
            # page loads / new SSE subscribers can be seeded) and forward it.
            self.state = r[1]

            # Log a play-history entry whenever the playing song changes.
            np = r[1].get("now_playing")
            if np and np.get("id") and np.get("id") != self._last_np_id:
                self._last_np_id = np.get("id")
                if self.ownerId:
                    try:
                        db.add(PlayHistory(
                            user_id=self.ownerId, song_id=str(np.get("id")),
                            title=np.get("title"), artist=np.get("artist"), cover=np.get("cover"),
                        ))
                        db.commit()
                    except Exception:
                        db.rollback()

            evt = dict(r[1])
            evt["type"] = "state"
            await sse.triggerEvent(f"pu_{self.id}", evt)

        elif r[0]=="progress":
            [_, pos, dur] = r

            await sse.triggerEvent(f"pu_{self.id}", {"type":"progress", "progress":pos, "duration":dur})

        elif r[0]=="audio_state":
            self.audio = r[1]
            evt = {"type": "audio_state", "audio": r[1]}
            await sse.triggerEvent(f"pu_{self.id}", evt)

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


# ── Unit settings / audio-device management (owner-gated) ──
from routes.auth import verify_token


def _owned_unit(unit_id, user, dbs):
    u: Unit = dbs.query(Unit).filter(Unit.id == unit_id).first()
    if not u:
        raise HTTPException(404, "Unit not found")
    if u.owner_id != user.id:
        raise HTTPException(403, "Not your unit")
    return u


@router.get("/{unit_id}/audio")
async def unit_audio(unit_id: str,
                     dbs: SessionLocal = Depends(get_db),  # type: ignore
                     user: User = Depends(verify_token)):
    u = _owned_unit(unit_id, user, dbs)
    uc = getUnitById(unit_id)
    return JSONResponse(content={"id": u.id, "name": u.name, "status": u.status,
                                 "online": uc is not None,
                                 "audio": uc.audio if uc else None})


async def _send_audio(unit_id, user, dbs, *cmd):
    _owned_unit(unit_id, user, dbs)
    uc = getUnitById(unit_id)
    if uc is None:
        raise HTTPException(503, "Unit is offline")
    await uc.send(["audio", *cmd])


@router.post("/{unit_id}/outputs")
async def unit_outputs(unit_id: str, body: UnitOutputsRequest,
                       dbs: SessionLocal = Depends(get_db),  # type: ignore
                       user: User = Depends(verify_token)):
    await _send_audio(unit_id, user, dbs, "set_outputs", body.sinks)
    return JSONResponse(content={"status": "ok"})


@router.post("/{unit_id}/sink_volume")
async def unit_sink_volume(unit_id: str, body: SinkVolumeRequest,
                           dbs: SessionLocal = Depends(get_db),  # type: ignore
                           user: User = Depends(verify_token)):
    await _send_audio(unit_id, user, dbs, "set_volume", body.sink, body.level)
    return JSONResponse(content={"status": "ok"})


@router.post("/{unit_id}/bt/{action}")
async def unit_bt(unit_id: str, action: str, body: BtRequest,
                  dbs: SessionLocal = Depends(get_db),  # type: ignore
                  user: User = Depends(verify_token)):
    if action not in ("scan", "pair", "connect", "disconnect", "remove"):
        raise HTTPException(400, "Unknown bluetooth action")
    if action == "scan":
        await _send_audio(unit_id, user, dbs, "bt_scan", body.seconds or 8)
    else:
        if not body.mac:
            raise HTTPException(400, "mac required")
        await _send_audio(unit_id, user, dbs, "bt_" + action, body.mac)
    return JSONResponse(content={"status": "ok"})


@router.patch("/{unit_id}")
async def unit_rename(unit_id: str, body: UnitRenameRequest,
                      dbs: SessionLocal = Depends(get_db),  # type: ignore
                      user: User = Depends(verify_token)):
    u = _owned_unit(unit_id, user, dbs)
    u.name = body.name
    dbs.commit()
    uc = getUnitById(unit_id)
    if uc:
        uc.name = body.name
    return JSONResponse(content={"status": "ok", "name": body.name})