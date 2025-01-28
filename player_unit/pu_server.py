import asyncio
import websockets
import random
import time
import json
import os
from enum import Enum

import configuration as cfg
import deezer as dz

import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


class Status(Enum):
    STARTING = 1
    STARTED = 2
    CONNECTED = 3
    PLAYING = 4
    PAUSED = 5

config = cfg.load_config("pu_config.ini")
STATUS = Status.STARTING

def rndId(l=4):
    al="ABCDEFGHIJKLMNPQRSTUVWXYZ123456789"
    random.seed(time.time())
    return(''.join([random.choice(al) for _ in range(l)]))

def quit():
    print("\n🔴 PlayerUnit stopped")
    exit()

async def runSocket():
    global STATUS

    uri = f"ws://{config['server']['host']}:{config['server']['port']}/unit"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                STATUS = Status.CONNECTED
                print("🟢 Connected to CentralServer")
                await ws.send(json.dumps(["id", config["player_unit"]["name"]]))

                while True:
                    try:
                        r = await ws.recv()
                        print(f"Received command: {r}")

                        r = json.loads(r)

                        if r[0]=="play":
                            print("Playing the music.")
                        elif r[0]=="pause":
                            print("Pausing the music.")
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

                            print(f"    ➤ Done")
                            
                    except KeyboardInterrupt:
                        quit()
                    except websockets.exceptions.ConnectionClosedError:
                        print("Got disconnected from the server, attempting to reconnect")
                        break
        except (websockets.exceptions.InvalidURI, ConnectionRefusedError, OSError) as e:
            time.sleep(5)
        except KeyboardInterrupt:
            quit()
        except Exception as e:
            time.sleep(5)
        time.sleep(5)

try:
    asyncio.run(runSocket())
except KeyboardInterrupt:
    quit()