import asyncio
import os
#from pydub import AudioSegment
#import simpleaudio as sa
from pathlib import Path
import threading
import pygame.mixer as mix
from mutagen.mp3 import MP3

#import pu_server as serv2
import pu_server2 as serv
import time

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
    print("🎵 Player ready to play")
    await serv.sendcmd(sws, ["status", "idle"])

    for _ in range(2):
        musics.append(Song("Doigby Guerrier", "songs/doigby_guerrier.mp3", "unknown_id", "https://mir-s3-cdn-cf.behance.net/project_modules/1400/fe529a64193929.5aca8500ba9ab.jpg"))
        musics.append(Song("Doigby Guerrier 2", "songs/doigby_guerrier.mp3", "unknown_id", "https://www.premadepixels.com/wp-content/uploads/2021/09/Rebirth-Album-Cover-PP1.jpg"))
        #musics.append(Song("La ferme", "songs/la_ferme.mp3", "unknown_id"))

    t1=asyncio.create_task(sendProgress())
    t2=asyncio.create_task(playerManager(sws))

    asyncio.gather(t1, t2)
    
    #await playerManager()

    #threading.Thread(target=playerManager, daemon=True).start()
    #threading.Thread(target=sendProgress, daemon=True).start()