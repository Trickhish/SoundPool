import asyncio
import os
#from pydub import AudioSegment
#import simpleaudio as sa
from pathlib import Path
import threading
import pygame.mixer as mix
from mutagen.mp3 import MP3

import pu_server as serv2
import pu_server2 as serv
import time

musics = []
msid = 0
playing = False
currentSong = None

class Song():
    def __init__(self, name, file, id):
        self.name = name
        self.file = file
        self.id = id
        self.duration = getSongDuration(file)

def getSongDuration(filename):
    audio = MP3(filename)
    return(audio.info.length*1000)

def isPlaying():
    return(mix.music.get_busy())

def playerManager():
    global playing
    global msid
    global currentSong

    while True:
        if (not playing) or isPlaying():
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
                
                asyncio.run(serv.send(["playing", m.id, m.name, m.duration]))
                asyncio.run(serv.send(["status", "playing"]))
            else:
                print(f"No more music to play")
                playing = False
                currentSong = None
                asyncio.run(serv.send(["status", "idle"]))
            msid+=1

def sendProgress():
    global currentSong
    
    while True:
        if (isPlaying()):
            pos = mix.music.get_pos()
            #print(pos)
            asyncio.run(serv.send(["progress", pos, currentSong.duration]))
            #await serv.send(["progress", pos])
            time.sleep(3)

# mix.music.set_volume(0-1)

async def runPlayer():
    global musics

    mix.init()
    print("🎵 Player ready to play")
    #await serv.send(["status", "idle"])

    for _ in range(2):
        musics.append(Song("Doigby Guerrier", "songs/doigby_guerrier.mp3", "unknown_id"))
        musics.append(Song("La ferme", "songs/la_ferme.mp3", "unknown_id"))

    threading.Thread(target=playerManager, daemon=True).start()
    threading.Thread(target=sendProgress, daemon=True).start()