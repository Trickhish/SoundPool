import time
from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from typing import AsyncGenerator
import asyncio
import json

from db_models import *
from routes.auth import verify_token

import pu_connection as puc

router = APIRouter()

clients = []

def getSseClient(uid):
    global clients

    return(any([cl.user.id==uid for cl in clients]))

def getSseClients(uid):
    global clients

    return([cl for cl in clients if cl.user.id==uid])

async def clientsTrigger(uid, evn, dt):
    for sc in getSseClients(uid):
        if sc!=None:
            await sc.trigger(evn, dt)

class sseClient():
    def __init__(self, user):
        self.events = []
        self.msgl = asyncio.Queue()
        self.user = user
    
    async def send(self, evn, msg):
        #json.dumps({
        #    "event": self.event,
        #    "data": msg
        #})
        await self.msgl.put("data: "+json.dumps([evn, msg]))

    async def trigger(self, evn, msg):
        if evn in self.events:
            asyncio.create_task(self.send(evn, msg))
        else:
            print(f"{self.user.username} is not subscribed to '{evn}'")

async def triggerEvent(evn, msg):
    global clients

    for cl in clients:
        if evn in cl.events:
            asyncio.create_task(cl.send(evn, msg))

_shutdown = False

def shutdown_all():
    global _shutdown
    _shutdown = True
    for cl in list(clients):
        try:
            cl.msgl.put_nowait(None)
        except Exception:
            pass

async def events_handler(user:User):
    global clients

    client = sseClient(user)
    clients.append(client)

    print(f"[SSE]: {user.username} is listening")

    try:
        while not _shutdown:
            msg = await client.msgl.get()
            if msg is None:
                break
            yield msg+"\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        print(f"[SSE]: {client.user.username} is no longer listening")
        if client in clients:
            clients.remove(client)


async def test_events():
    while True:
        await triggerEvent("test", str(time.time()))
        await asyncio.sleep(3)



@router.get("/subscribe/{event_name}")
async def sse_sub(event_name: str, user: User = Depends(verify_token)):
    global clients

    cll = getSseClients(user.id)

    #client = getSseClient(user.id)
    #if client==None:
    #    raise HTTPException(status_code=400, detail=f"You are not listening to SSE requests")

    if len(cll)==0:
        raise HTTPException(status_code=400, detail=f"You are not listening to SSE requests")
    
    for cl in cll:
        cl.events.append(event_name)

    print(f"[SSE]: {user.username} subscribed to '{event_name}'")

    # Seed the new subscriber with the player's current snapshot so a fresh
    # page load is instantly correct (cover/title/queue/position) instead of
    # waiting for the next change.
    if event_name.startswith("pu_"):
        uc = puc.getUnitById(event_name[3:])
        if uc is not None and uc.state is not None:
            snapshot = dict(uc.state)
            snapshot["type"] = "state"
            for cl in cll:
                await cl.send(event_name, snapshot)

    

    return(JSONResponse(content="Subscribed successfully"))

@router.get("/sse")
async def sse(user: User = Depends(verify_token)):
    return StreamingResponse(events_handler(user), media_type="text/event-stream")
