import asyncio
import os
import json
#from pydub import AudioSegment
#import simpleaudio as sa
from pathlib import Path
import threading
import pygame.mixer as mix
from mutagen.mp3 import MP3

#import pu_server as serv2
import pu_server2 as serv
import time

# Persistent queue manifest — kept in the unit user's home (NOT in /tmp, and
# not in the root-owned install dir) so the queue survives a service restart.
# Songs whose files no longer exist (e.g. after a reboot clears /tmp) are
# skipped on restore.
QUEUE_STATE_DIR = os.path.join(os.path.expanduser("~"), ".soundpool")
QUEUE_STATE_FILE = os.path.join(QUEUE_STATE_DIR, "queue_state.json")

musics = []
msid = 0
playing = False
currentSong = None
sws = None

class Song():
    def __init__(self, name, file, id, img_url):
        self.name = name
        self.file = file
        self.id = id
        self.duration = getSongDuration(file)
        self.img_url = img_url

def save_queue():
    try:
        os.makedirs(QUEUE_STATE_DIR, exist_ok=True)
        data = {
            "msid": msid,
            "musics": [
                {"name": m.name, "file": m.file, "id": m.id, "img_url": m.img_url}
                for m in musics
            ],
        }
        with open(QUEUE_STATE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as ex:
        print(f"⚠️ Failed to save queue state: {ex}")

def load_queue():
    global musics, msid

    if not os.path.exists(QUEUE_STATE_FILE):
        return

    try:
        with open(QUEUE_STATE_FILE) as f:
            data = json.load(f)
    except Exception as ex:
        print(f"⚠️ Failed to read queue state: {ex}")
        return

    saved_msid = data.get("msid", 0)
    adjusted_msid = saved_msid
    restored = []
    for i, e in enumerate(data.get("musics", [])):
        ok = False
        if not os.path.exists(e["file"]):
            print(f"⚠️ Queued file missing, skipping: {e['file']}")
        else:
            try:
                restored.append(Song(e["name"], e["file"], e["id"], e["img_url"]))
                ok = True
            except Exception as ex:
                print(f"⚠️ Skipping '{e.get('name')}': {ex}")
        # Keep the playback position pointing at the same upcoming song by
        # shifting it down for every dropped entry that preceded it.
        if not ok and i < saved_msid:
            adjusted_msid -= 1

    musics = restored
    msid = max(0, min(adjusted_msid, len(musics)))

    if musics:
        print(f"🔁 Restored {len(musics)} queued song(s) from previous session")

def sendcmd(cmd):
    global sws

    serv.sendcmd(sws, cmd)

def getSongDuration(filename):
    audio = MP3(filename)
    return(audio.info.length*1000)

def isPlaying():
    return(mix.music.get_busy())

async def playerManager(ws):
    global playing
    global msid
    global currentSong

    while True:
        if (not playing) or isPlaying():
            await asyncio.sleep(0.1)
            continue
        print(f"Music ended")

        if musics!=[]:
            if msid<0:
                msid=0
            
            if msid<len(musics):
                m:Song = musics[msid]
                print(f"Playing {m.name}")
                currentSong = m
                mix.music.load(m.file)
                mix.music.play()
                #await serv.send(["playing", m.id, m.name])
                
                await serv.sendcmd(ws, ["playing", m.id, m.name, m.duration, m.img_url])
                await serv.sendcmd(ws, ["status", "playing"])

                #asyncio.run(serv.send(["playing", m.id, m.name, m.duration]))
                #asyncio.run(serv.send(["status", "playing"]))
            else:
                print(f"No more music to play")
                playing = False
                currentSong = None
                asyncio.run(serv.send(["status", "idle"]))
            msid+=1
            save_queue()
        else:
            playing=False
        
        await asyncio.sleep(0.01)

async def sendProgress():
    global currentSong
    global sws

    #while True:
    #    await serv.sendcmd(sws, ["progress", "1", "2"])
    #    await asyncio.sleep(1)
    
    while True:
        if (isPlaying()):
            pos = mix.music.get_pos()
            #print(pos)
            await serv.sendcmd(sws, ["progress", currentSong.name, currentSong.id, pos, currentSong.duration, currentSong.img_url])
            
            #await serv.sendcmd(sws, ["progress", pos, currentSong.duration])
            #asyncio.run(serv.sendcmd(sws, ["progress", pos, currentSong.duration]))
            #asyncio.run(serv.send(["progress", pos, currentSong.duration]))
            #await serv.send(["progress", pos])
        await asyncio.sleep(1)

# mix.music.set_volume(0-1)

async def runPlayer(player):
    global musics
    global sws

    sws = player.ws

    mix.init()
    load_queue()
    print("🎵 Player ready to play")
    await serv.sendcmd(sws, ["status", "idle"])

    t1=asyncio.create_task(sendProgress())
    t2=asyncio.create_task(playerManager(sws))

    asyncio.gather(t1, t2)
    
    #await playerManager()

    #threading.Thread(target=playerManager, daemon=True).start()
    #threading.Thread(target=sendProgress, daemon=True).start()