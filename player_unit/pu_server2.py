import asyncio
# Python 3.8 lacks asyncio.to_thread (added in 3.9); back-port it so the unit
# runs on stock Ubuntu 20.04 Python. No-op on 3.9+.
if not hasattr(asyncio, "to_thread"):
    import functools as _functools
    async def _to_thread(func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _functools.partial(func, *args, **kwargs))
    asyncio.to_thread = _to_thread
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
import audio_devices as ad

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

for _d in ["songs", "albums", "playlists"]:
    os.makedirs(config["download_dirs"][_d], exist_ok=True)
STATUS = Status.STARTING
tosend = asyncio.Queue()
msgl = []

# Bounded download pool: songs are queued instantly as placeholders and
# downloaded a few at a time IN ORDER, so the earliest songs become playable
# quickly instead of 16 downloads crawling in parallel.
download_queue = asyncio.Queue()
DOWNLOAD_WORKERS = 3

async def emit_audio_state():
    try:
        state = await asyncio.to_thread(ad.audio_state)
        if mp.sws is not None:
            await sendcmd(mp.sws, ["audio_state", state])
    except Exception as ex:
        print(f"[audio] emit failed: {ex}")


async def handle_audio(r):
    cmd = r[1]
    try:
        if cmd == "set_outputs":
            await asyncio.to_thread(ad.set_outputs, r[2])
        elif cmd == "set_volume":
            await asyncio.to_thread(ad.set_sink_volume, r[2], r[3])
        elif cmd == "test":
            ad.test_output(r[2] if len(r) > 2 else None)  # non-blocking beep
        elif cmd == "bt_scan":
            ad.bt_scan(int(r[2]) if len(r) > 2 else 8)  # async; notifies when done
        elif cmd == "bt_pair":
            await asyncio.to_thread(ad.bt_pair, r[2])
        elif cmd == "bt_connect":
            await asyncio.to_thread(ad.bt_connect, r[2])
        elif cmd == "bt_disconnect":
            await asyncio.to_thread(ad.bt_disconnect, r[2])
        elif cmd == "bt_remove":
            await asyncio.to_thread(ad.bt_remove, r[2])
    except Exception as ex:
        print(f"[audio] command {cmd} failed: {ex}")
    await emit_audio_state()


def _render_path(song):
    """Where a rendered track lives on disk. Shared by render and prefetch so a
    prefetched file is actually found when the track starts."""
    return os.path.join(config["download_dirs"]["songs"],
                        song["ART_NAME"] + " - " + song["SNG_TITLE"] + ".mp3")


_prefetching = set()


async def do_prefetch(song, url, key):
    """Download the upcoming track ahead of time.

    Without this the unit downloaded the whole MP3 only when the track started
    (measured 4-20s), and because the room's clock kept running it then had to
    start that far into the song.
    """
    path = _render_path(song)
    sid = song.get("SNG_ID", "")
    if os.path.exists(path) or sid in _prefetching:
        return
    _prefetching.add(sid)
    try:
        await dz.downloadSong(song, url, key, path,
                              config["player_unit"]["download_covers"].lower() == "true",
                              config["player_unit"]["cover_size"])
        print(f"⏭️  Prefetched: {song['SNG_TITLE']}")
    except Exception as ex:
        print(f"    ✖ Prefetch failed for {song.get('SNG_TITLE')}: {ex}")
        try:
            if os.path.exists(path):
                os.remove(path)      # don't leave a truncated file to be played
        except Exception:
            pass
    finally:
        _prefetching.discard(sid)


async def do_render(song, url, key, pos_ms, playing, vol=None):
    """Act as a room output: play exactly what the server's room conductor
    dictates (track + position + playing + master volume), downloading on demand."""
    # The websocket is live before runPlayer() initialises the backend, so a
    # render can land on an uninitialised player right after startup. init() is
    # a no-op once initialised, so just make sure it's ready here.
    try:
        if not mp.audio.get_init():
            mp.audio.init()
    except Exception as ex:
        print(f"    ✖ Audio backend init failed: {ex}")
        return

    if vol is not None:
        mp.volume = max(0.0, min(1.0, float(vol)))
    mp.render_mode = True
    mp.render_seq += 1
    myseq = mp.render_seq

    song_name = song["SNG_TITLE"]
    artist = song["ART_NAME"]
    song_id = song.get("SNG_ID", "")
    path = _render_path(song)
    t_recv = time.monotonic()

    # If a prefetch of this track is still running, wait for it instead of
    # starting a second download of the same file.
    if song_id in _prefetching:
        for _ in range(600):                 # up to ~60s
            await asyncio.sleep(0.1)
            if song_id not in _prefetching:
                break

    if song_id != mp.render_current or not os.path.exists(path):
        if not os.path.exists(path):
            print(f"💿 Rendering (downloading): {song_name}...")
            try:
                await dz.downloadSong(song, url, key, path,
                            config["player_unit"]["download_covers"].lower() == "true",
                            config["player_unit"]["cover_size"])
            except Exception as ex:
                print(f"    ✖ Render download failed: {ex}")
                return
        if myseq != mp.render_seq:
            return  # a newer render arrived while downloading
        # compensate for download time to stay near the room timeline
        start = (pos_ms + (time.monotonic() - t_recv) * 1000.0) / 1000.0 if playing else pos_ms / 1000.0
        try:
            mp.audio.play(start=max(0.0, start), path=path)
            mp.audio.set_volume(mp.volume)
            # Only claim the track once it's really loaded: setting this before
            # the load meant a failed load (e.g. a render arriving before the
            # mixer finished initialising) left us thinking the song was ready,
            # so every later render took the "already loaded" path and failed
            # with "music not loaded" — playback never recovered.
            mp.render_current = song_id
            mp.render_paused = not playing
            mp.render_pause_ms = pos_ms
            if not playing:
                mp.audio.pause()
        except Exception as ex:
            mp.render_current = None   # force a full reload on the next render
            print(f"    ✖ Render play failed: {ex}")
            return
        print(f"🔊 Rendering: {song_name} @ {int(max(0.0, start)*1000)}ms playing={playing}")
        # Tell the room we have this track loaded. While units are loading the
        # server holds the clock, so it only starts once every unit is ready —
        # that's what stops a slow download starting the song part-way in.
        try:
            if mp.sws is not None:
                await sendcmd(mp.sws, ["ready", song_id])
        except Exception as ex:
            print(f"    ✖ ready report failed: {ex}")
    else:
        # Same track already loaded — resume/seek/pause.
        try:
            if playing:
                # A plain resume asks for the position we paused at, so
                # unpause rather than re-seek: no decoder restart, no glitch.
                resuming = mp.render_paused and abs(pos_ms - mp.render_pause_ms) < 2000
                if resuming:
                    mp.audio.unpause()
                else:
                    mp.audio.seek(pos_ms / 1000.0)
                mp.audio.set_volume(mp.volume)
                mp.render_paused = False
            else:
                mp.audio.pause()
                mp.render_paused = True
                mp.render_pause_ms = pos_ms
        except Exception as ex:
            # Don't get stuck: drop the "already loaded" assumption so the next
            # render reloads the track from scratch.
            print(f"    ✖ Render update failed: {ex} — will reload")
            mp.render_current = None


async def download_worker():
    while True:
        song_obj, song, url, key, autoplay = await download_queue.get()
        print(f"💿 Downloading for queue: {song_obj.name}...")
        try:
            await dz.downloadSong(song, url, key, song_obj.file,
                        config["player_unit"]["download_covers"].lower()=="true",
                        config["player_unit"]["cover_size"])
        except Exception as ex:
            print(f"    ✖ Download failed for {song_obj.name}: {ex}")
            song_obj.failed = True
            mp.emit_state()
            download_queue.task_done()
            continue
        song_obj.ready = True
        song_obj.duration = mp.getSongDuration(song_obj.file)
        mp.save_queue()
        print(f"    ➤ Queued: {song_obj.name}")
        # Only auto-start from a truly idle player (nothing playing AND no
        # current/paused song) — never resume over a pause.
        if autoplay and not mp.playing and mp.currentSong is None:
            mp.playing = True
        mp.emit_state()
        download_queue.task_done()

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
    if player!=None:
        pl=player
        await player.send(cmd)



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
            print(f"The id '{config['player_unit']['uid']}' isn't registered in the central server.\nIf you want to reset the id, delete it in the configuration and restart this unit.")
        #    await ws.send(json.dumps(["ask_id", config["player_unit"]["name"]]))
    elif r[0]=="control":
        if r[1]=="play":
            print("Playing the music.")
            mp.playing=True
            mp.audio.unpause()
            await sendcmd(ws, ["status", "playing"])
            mp.emit_state()
        elif r[1]=="pause":
            print("Pausing the music.")
            mp.playing=False
            mp.audio.pause()
            await sendcmd(ws, ["status", "paused"])
            mp.emit_state()
        elif r[1]=="prev":
            print("Loading previous song.")
            mp._manual_skip = True
            mp.playing = True   # load & play even if currently paused/idle
            mp.msid-=2
            mp.audio.stop()
            await sendcmd(ws, ["status", "loading"])
        elif r[1]=="next":
            print("Loading next song.")
            mp._manual_skip = True
            mp.playing = True   # load & play even if currently paused/idle
            mp.audio.stop()
            await sendcmd(ws, ["status", "loading"])
        elif r[1]=="seek":
            print(f"Seeking to {r[2]}%.")
            mp.seek(r[2])
        elif r[1]=="volume":
            print(f"Setting volume to {r[2]}.")
            mp.set_volume(r[2])
        elif r[1]=="shuffle":
            print(f"Setting shuffle to {r[2]}.")
            mp.set_shuffle(r[2])
        elif r[1]=="repeat":
            print(f"Setting repeat to {r[2]}.")
            mp.set_repeat(r[2])
        elif r[1]=="clear":
            print("Clearing queue.")
            mp.musics.clear()
            mp.msid = 0
            mp.current_index = -1
            mp.audio.stop()
            mp.playing = False
            mp.currentSong = None
            mp.save_queue()
            await sendcmd(ws, ["status", "idle"])
            mp.emit_state()
    elif r[0]=="queue_add":
        # Optional 5th element: whether to start playback once queued. Defaults
        # to True for backward compat; the server sends False for playlist loads
        # so they only fill the queue (and a completing download never overrides
        # a user's pause).
        _,song,url,key,*rest = r
        autoplay = rest[0] if rest else True
        song_name = song["SNG_TITLE"]
        artist_name = song["ART_NAME"]
        album_name = song.get("ALB_TITLE", "")
        pic = song.get("ALB_PICTURE", "")
        img_url = f"https://e-cdns-images.dzcdn.net/images/cover/{pic}/500x500-000000-80-0-0.jpg" if pic else ""
        song_path = os.path.join(config["download_dirs"]["songs"], artist_name+" - "+song_name+".mp3")

        # Add the song to the queue immediately as a pending placeholder so it
        # shows up right away; the bounded download pool fetches it in order.
        song_obj = mp.Song(song_name, song_path, song.get("SNG_ID", ""),
                           img_url, artist_name, album_name, ready=False)
        mp.musics.append(song_obj)
        mp.emit_state()
        await download_queue.put((song_obj, song, url, key, autoplay))
    elif r[0]=="render":
        _,song,url,key,pos_ms,playing,*rest = r
        vol = rest[0] if rest else None
        asyncio.create_task(do_render(song, url, key, pos_ms, playing, vol))
    elif r[0]=="prefetch":
        _,song,url,key = r
        asyncio.create_task(do_prefetch(song, url, key))
    elif r[0]=="stop":
        print("⏹ Detached from room — stopping.")
        mp.render_stop()
    elif r[0]=="audio":
        asyncio.create_task(handle_audio(r))
    elif r[0]=="queue_remove":
        print(f"Removing queue item {r[1]}.")
        mp.queue_remove(r[1])
    elif r[0]=="queue_move":
        print(f"Moving queue item {r[1]} -> {r[2]}.")
        mp.queue_move(r[1], r[2])
    elif r[0]=="queue_jump":
        print(f"Jumping to queue item {r[1]}.")
        mp.queue_jump(r[1])
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
        scheme = "wss" if config["server"].get("wss", "false").lower() == "true" else "ws"
        self.uri = uri = f"{scheme}://{config['server']['host']}:{config['server']['port']}/unit"
        self.tosend = asyncio.Queue()
        self.ws = None
        self.ready_event = asyncio.Event()
    
    async def send(self, msg):
        print(f"Sending {msg}")
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

                # Point the player at the live socket so state/progress sent
                # from music_player survive reconnects (e.g. server restarts).
                mp.sws = self.ws

                self.ready_event.set()
                
                if (config["player_unit"]["uid"]):
                    await self.send(["id", config["player_unit"]["uid"], config["player_unit"]["name"], config["player_unit"]["owner_mail"]])
                else:
                    await self.send(["ask_id", config["player_unit"]["name"], config["player_unit"]["owner_mail"]])

                asyncio.create_task(emit_audio_state())  # report audio devices on connect
                
                while True:
                    try:
                        ro = await self.ws.recv()

                        print(ro)
                        await receiveHandler(self.ws, ro)
                            
                    except KeyboardInterrupt:
                        quit()
                    except websockets.exceptions.ConnectionClosedError as ex:
                        print(ex)
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
    task1 = asyncio.create_task(player.run())
    await player.ready_event.wait()

    # let async audio events (e.g. BT scan completion, USB plug/unplug) push fresh state
    loop = asyncio.get_running_loop()
    ad.set_notify(lambda: asyncio.run_coroutine_threadsafe(emit_audio_state(), loop))
    # Re-apply the saved output choice: it used to be in-memory only, so after a
    # restart the unit quietly played to the system default sink instead.
    try:
        await asyncio.to_thread(ad.load_selected)
    except Exception as ex:
        print(f"[audio] restoring outputs failed: {ex}")
    threading.Thread(target=ad.watch_sinks, daemon=True).start()

    workers = [asyncio.create_task(download_worker()) for _ in range(DOWNLOAD_WORKERS)]
    task2 = asyncio.create_task(mp.runPlayer(player))

    await asyncio.gather(task1, task2, *workers)

if __name__ == "__main__":
    # Reuse the default event loop rather than asyncio.run(), which spins up a
    # fresh loop. Module-level asyncio primitives (the queues/events created at
    # import time) bind to the default loop, so a new loop breaks them on
    # Python 3.8 ("attached to a different loop"). This path works on 3.8–3.11.
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        quit()