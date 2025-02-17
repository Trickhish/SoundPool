import json
from typing import List
from uuid import uuid4
from fastapi import WebSocket, WebSocketDisconnect

import deezer as dz
import tracks_manager as tm

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
    
    async def received(self, msg):
        r = json.loads(r)
        print(r)

        if (r[0]=="id"):
            pun = r[1]
            thisPlayerUnit.name = pun
            print(f"📯🚀 Identified PU_{thisPlayerUnit.id[:4]} as {pun}")

            await asyncio.to_thread(thisPlayerUnit.sendTest)

        #await websocket.send_text(f"Command received: {data}")

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
            thisPlayerUnit.received(r)
            
    except WebSocketDisconnect:
        units.remove(thisPlayerUnit)
        print(f"🚨 PlayerUnit {thisPlayerUnit.id[:4]} disconnected")

@app.post("/send_command/")
async def send_command(command: str):
    for u in units:
        await u.send_text(command)
    return {"message": "Command sent to all players"}