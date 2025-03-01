import asyncio
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

def rndId(l=4):
    al="ABCDEFGHIJKLMNPQRSTUVWXYZ123456789"
    random.seed(time.time())
    return(''.join([random.choice(al) for _ in range(l)]))

def quit():
    print("\n🔴 PlayerUnit stopped")
    exit()

async def sendcmd(ws, cmd):
    await ws.send(json.dumps(cmd))

async def runSocket():
    global STATUS

    print(f"Trying to connect to {config['server']['host']}:{config['server']['port']}")

    uri = f"ws://{config['server']['host']}:{config['server']['port']}/unit"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                STATUS = Status.CONNECTED
                print("🟢 Connected to CentralServer")
                if (config["player_unit"]["uid"]):
                    await ws.send(json.dumps(["id", config["player_unit"]["uid"], config["player_unit"]["name"], config["player_unit"]["owner_mail"]]))
                else:
                    await ws.send(json.dumps(["ask_id", config["player_unit"]["name"], config["player_unit"]["owner_mail"]]))

                while True:
                    try:
                        ro = await ws.recv()

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
                                mp.mix.music.play()
                                await sendcmd(ws, ["status", "playing"])
                            elif r[1]=="pause":
                                print("Pausing the music.")
                                mp.playing=False
                                mp.mix.music.pause()
                                await sendcmd(ws, ["status", "paused"])
                            elif r[1]=="prev":
                                print("Loading previous song.")
                                await sendcmd(ws, ["status", "loading"])
                            elif r[1]=="next":
                                print("Loading next song.")
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

async def main():
    #player = mp.AsyncPlayer()

    task1 = asyncio.create_task(runSocket())
    task2 = asyncio.create_task(mp.runPlayer())

    await asyncio.gather(task1, task2)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        quit()