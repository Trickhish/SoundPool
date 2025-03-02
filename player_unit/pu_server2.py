import asyncio
import threading
import websockets
import random
import time
import json
import os
from enum import Enum

import configuration as cfg
import deezer2 as dz
import music_player as mp

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Status(Enum):
    STARTING = 1
    STARTED = 2
    CONNECTED = 3
    PLAYING = 4
    PAUSED = 5

CONFIG_FILE = "pu_config.ini"
config = cfg.load_config(CONFIG_FILE)
STATUS = Status.STARTING
tosend = asyncio.Queue()
msgl = []

def rndId(l=4):
    al="ABCDEFGHIJKLMNPQRSTUVWXYZ123456789"
    random.seed(time.time())
    return(''.join([random.choice(al) for _ in range(l)]))

def quit():
    print("\n🔴 PlayerUnit stopped")
    exit()

async def sendcmd(ws, cmd):

    await ws.send(json.dumps(cmd))

async def send(cmd):
    print(player)
    
    if player!=None:
        await player.tosend.put(cmd)
        #await player.send(cmd)
    
    #await tosend.put(cmd)
    #print(cmd, tosend.qsize())
    #msgl.append(cmd)



async def senderHandler(ws):
    #global msgl
    
    print("SENDER HANDLING")
    
    while True:
        try:
            #if msgl!=[]:
            #    m = msgl.pop()
            #    print(f"Sending {m}")
            #    await sendcmd(ws, m)
            #print("Waiting for a message to send")
            if not tosend.empty():
                msg = await tosend.get()
                
                print(f"Sending {msg}")
                await sendcmd(ws, msg)
                tosend.task_done()
        except Exception as ex:
            print(f"Error: {ex}")
        
        await asyncio.sleep(3)



async def receiveHandler(ws, ro):
    r = json.loads(ro)
    
    if r[0]=="id_assign":
        mid = r[1]
        print(f"I've been assigned the id '{mid}'")

        config["player_unit"]["uid"] = mid
        cfg.write_config(config, CONFIG_FILE)
    elif r[0]=="error":
        err_name = r[1]
        if err_name=="unknown_id":
            print(f"The id '{config["player_unit"]["uid"]}' isn't registered in the central server.\nIf you want to reset the id, delete it in the configuration and restart this unit.")
        #    await ws.send(json.dumps(["ask_id", config["player_unit"]["name"]]))
    elif r[0]=="control":
        if r[1]=="play":
            print("Playing the music.")
            mp.playing=True
            mp.mix.music.unpause()
            await sendcmd(ws, ["status", "playing"])
        elif r[1]=="pause":
            print("Pausing the music.")
            mp.playing=False
            mp.mix.music.pause()
            await sendcmd(ws, ["status", "paused"])
        elif r[1]=="prev":
            print("Loading previous song.")
            mp.msid-=2
            mp.mix.music.stop()
            await sendcmd(ws, ["status", "loading"])
        elif r[1]=="next":
            print("Loading next song.")
            mp.mix.music.stop()
            await sendcmd(ws, ["status", "loading"])
    elif r[0]=="download":
        _,song,url,key = r

        song_name = song["SNG_TITLE"]
        artist_name = song["ART_NAME"]
        song_path = os.path.join(config["download_dirs"]["songs"], artist_name+" - "+song_name+".mp3")

        print(f"💿 Donwloading {song_name} ...")

        await dz.downloadSong(song,url,key,
                    song_path,
                    config["player_unit"]["download_covers"].lower()=="true",
                    config["player_unit"]["cover_size"]
        )

        print(f"    ➤ Done - {song_path}")
    else:
        print(f"Received command: {ro}")
        



class PlayerServer():
    def __init__(self):
        self.uri = uri = f"ws://{config['server']['host']}:{config['server']['port']}/unit"
        self.tosend = asyncio.Queue()
        self.ws = None
    
    async def send(self, msg):
        await self.ws.send(json.dumps(msg))
    
    async def msgHandler(self):
        print("Handling Messages")
        while True:
            msg = await self.tosend.get()
            print(msg)
            await asyncio.sleep(3)
            
    async def run(self):
        print(f"Trying to connect to {config['server']['host']}:{config['server']['port']}")

        while True:
            try:
                self.ws = await websockets.connect(self.uri)
                STATUS = Status.CONNECTED
                print("🟢 Connected to CentralServer")
                
                if (config["player_unit"]["uid"]):
                    await self.send(["id", config["player_unit"]["uid"], config["player_unit"]["name"], config["player_unit"]["owner_mail"]])
                else:
                    await self.send(["ask_id", config["player_unit"]["name"], config["player_unit"]["owner_mail"]])
                
                while True:
                    try:
                        ro = await self.ws.recv()

                        await receiveHandler(self.ws, ro)
                            
                    except KeyboardInterrupt:
                        quit()
                    except websockets.exceptions.ConnectionClosedError:
                        print("Got disconnected from the server, attempting to reconnect")
                        break
                
            except (websockets.exceptions.InvalidURI, ConnectionRefusedError, OSError) as e:
                print(e)
                time.sleep(5)
            except KeyboardInterrupt:
                quit()
            except Exception as e:
                print(e)
                time.sleep(5)
            time.sleep(5)


player = PlayerServer()

async def main():
    #player = mp.AsyncPlayer()
    task1 = asyncio.create_task(player.run())
    task3 = asyncio.create_task(player.msgHandler())
    #task1 = asyncio.create_task(runSocket())
    task2 = asyncio.create_task(mp.runPlayer())

    await asyncio.gather(task1, task2, task3)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()