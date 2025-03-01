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

async def events_handler(user:User):
    global clients

    client = sseClient(user)
    clients.append(client)

    #client = getSseClient(user.id)
    #if client==None:
    #    client = sseClient(user)
    #    clients.append(client)
    
    #client.events.append(evn)

    print(f"[SSE]: {user.username} is listening")
    
    try:
        while True:
            msg = await client.msgl.get()
            yield msg+"\n\n"
    except asyncio.CancelledError:
        print(f"[SSE]: {client.user.username} is no longer listening")
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

    

    return(JSONResponse(content="Subscribed successfully"))

@router.get("/sse")
async def sse(user: User = Depends(verify_token)):
    return StreamingResponse(events_handler(user), media_type="text/event-stream")
