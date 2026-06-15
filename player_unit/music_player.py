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
msid = 0                 # index of the NEXT song to play
current_index = -1       # index in `musics` of the song currently loaded
playing = False
currentSong = None
sws = None
play_offset_ms = 0       # base offset of the current play() call (for seek + absolute position)

# Playback options (persisted across restarts)
volume = 1.0
shuffle = False
repeat = "off"           # off | all | one
_manual_skip = False     # set by prev/next so repeat-one doesn't replay instead

class Song():
    def __init__(self, name, file, id, img_url, artist="", album="", ready=True):
        self.name = name
        self.file = file
        self.id = id
        self.img_url = img_url
        self.artist = artist
        self.album = album
        self.failed = False
        # A song is only playable once its file is on disk. Placeholders for
        # still-downloading songs are added to the queue immediately (so they
        # show up) with ready=False, then marked ready once downloaded.
        self.ready = bool(ready and file and os.path.exists(file))
        self.duration = getSongDuration(file) if self.ready else 0

def save_queue():
    try:
        os.makedirs(QUEUE_STATE_DIR, exist_ok=True)
        data = {
            "msid": msid,
            "volume": volume,
            "shuffle": shuffle,
            "repeat": repeat,
            "musics": [
                {"name": m.name, "file": m.file, "id": m.id, "img_url": m.img_url,
                 "artist": m.artist, "album": m.album}
                for m in musics if m.ready  # only persist fully-downloaded songs
            ],
        }
        with open(QUEUE_STATE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as ex:
        print(f"⚠️ Failed to save queue state: {ex}")

def load_queue():
    global musics, msid, volume, shuffle, repeat

    if not os.path.exists(QUEUE_STATE_FILE):
        return

    try:
        with open(QUEUE_STATE_FILE) as f:
            data = json.load(f)
    except Exception as ex:
        print(f"⚠️ Failed to read queue state: {ex}")
        return

    volume = data.get("volume", 1.0)
    shuffle = data.get("shuffle", False)
    repeat = data.get("repeat", "off")

    saved_msid = data.get("msid", 0)
    adjusted_msid = saved_msid
    restored = []
    for i, e in enumerate(data.get("musics", [])):
        ok = False
        if not os.path.exists(e["file"]):
            print(f"⚠️ Queued file missing, skipping: {e['file']}")
        else:
            try:
                restored.append(Song(e["name"], e["file"], e["id"], e["img_url"],
                                     e.get("artist", ""), e.get("album", "")))
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


def current_position():
    """Absolute playback position (ms) within the current song."""
    if currentSong is None:
        return 0
    p = mix.music.get_pos()  # ms since the last play(); -1 when not playing
    if p < 0:
        p = 0
    return play_offset_ms + p


def state_dict():
    """Full authoritative snapshot of the player, sent to the central server."""
    return {
        "now_playing": ({
            "id": currentSong.id,
            "title": currentSong.name,
            "artist": currentSong.artist,
            "album": currentSong.album,
            "cover": currentSong.img_url,
            "duration": currentSong.duration,
        } if currentSong else None),
        "position": current_position(),
        "playing": bool(playing),
        "current_index": current_index,
        "msid": msid,
        "volume": volume,
        "shuffle": shuffle,
        "repeat": repeat,
        "queue": [
            {"key": i, "id": m.id, "title": m.name, "artist": m.artist,
             "cover": m.img_url, "duration": m.duration,
             "ready": m.ready, "failed": m.failed}
            for i, m in enumerate(musics)
        ],
    }


def emit_state():
    """Schedule sending the full state snapshot to the server (non-blocking)."""
    if sws is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(serv.sendcmd(sws, ["state", state_dict()]))


def seek(percent):
    """Seek within the current song to `percent` (0..100) of its duration."""
    global play_offset_ms, playing
    if currentSong is None:
        return
    seconds = max(0.0, (float(percent) / 100.0) * (currentSong.duration / 1000.0))
    try:
        mix.music.play(start=seconds)
        mix.music.set_volume(volume)
        play_offset_ms = int(seconds * 1000)
        playing = True
    except Exception as ex:
        print(f"⚠️ Seek failed: {ex}")
        return
    emit_state()

def set_volume(level):
    """Set playback volume (0.0..1.0) and apply it to the current stream."""
    global volume
    volume = max(0.0, min(1.0, float(level)))
    try:
        mix.music.set_volume(volume)
    except Exception:
        pass
    save_queue()
    emit_state()


def set_shuffle(on):
    """Toggle shuffle. Enabling randomizes the order of the upcoming songs."""
    global shuffle
    shuffle = bool(on)
    if shuffle and msid < len(musics):
        import random
        upcoming = musics[msid:]
        random.shuffle(upcoming)
        musics[msid:] = upcoming
    save_queue()
    emit_state()


def set_repeat(mode):
    """Set repeat mode: off | all | one."""
    global repeat
    if mode in ("off", "all", "one"):
        repeat = mode
    save_queue()
    emit_state()


def queue_remove(index):
    """Remove the song at `index` from the queue."""
    global msid, current_index
    if not (0 <= index < len(musics)):
        return
    del musics[index]
    if index < msid:
        msid -= 1
    if index < current_index:
        current_index -= 1
    save_queue()
    emit_state()


def queue_move(frm, to):
    """Move the song at `frm` to land at original position `to`."""
    if not (0 <= frm < len(musics)):
        return
    item = musics.pop(frm)
    if frm < to:
        to -= 1  # account for the removed item shifting later indices down
    to = max(0, min(to, len(musics)))
    musics.insert(to, item)
    save_queue()
    emit_state()


def queue_jump(index):
    """Jump to and start playing the song at `index`."""
    global msid, playing, _manual_skip
    if not (0 <= index < len(musics)):
        return
    _manual_skip = True
    msid = index
    playing = True
    mix.music.stop()  # playerManager will load musics[msid] next
    emit_state()


def sendcmd(cmd):
    global sws

    serv.sendcmd(sws, cmd)

def getSongDuration(filename):
    audio = MP3(filename)
    return(audio.info.length*1000)

def isPlaying():
    return(mix.music.get_busy())

async def playerManager(ws):
    global playing, msid, currentSong, current_index, play_offset_ms, _manual_skip

    while True:
        if (not playing) or isPlaying():
            await asyncio.sleep(0.1)
            continue

        # The current song has finished (or nothing is loaded yet).
        # repeat-one: replay the same song, unless the user pressed prev/next.
        if repeat == "one" and not _manual_skip and currentSong is not None and current_index >= 0:
            msid = current_index
        _manual_skip = False

        if msid < 0:
            msid = 0

        # repeat-all: wrap back to the start once the queue is exhausted.
        if repeat == "all" and musics and msid >= len(musics):
            msid = 0

        if musics and msid < len(musics):
            m: Song = musics[msid]
            if m.failed:
                print(f"Skipping failed song: {m.name}")
                msid += 1
                continue
            if not m.ready:
                # Next song is still downloading — wait for it (don't advance).
                await asyncio.sleep(0.2)
                continue
            current_index = msid
            currentSong = m
            print(f"Playing {m.name}")
            mix.music.load(m.file)
            mix.music.play()
            mix.music.set_volume(volume)
            play_offset_ms = 0
            msid += 1
            save_queue()
            await serv.sendcmd(ws, ["status", "playing"])
            emit_state()
        elif playing:
            print("No more music to play")
            playing = False
            currentSong = None
            current_index = -1
            await serv.sendcmd(ws, ["status", "idle"])
            emit_state()

        await asyncio.sleep(0.05)

async def sendProgress():
    global sws

    n = 0
    while True:
        if isPlaying() and currentSong is not None:
            await serv.sendcmd(sws, ["progress", current_position(), currentSong.duration])
        n += 1
        if n % 5 == 0:
            # Periodic full-state heartbeat: self-heals any client/unit desync
            # caused by a dropped event, without waiting for the next change.
            emit_state()
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
    emit_state()

    t1=asyncio.create_task(sendProgress())
    t2=asyncio.create_task(playerManager(sws))

    asyncio.gather(t1, t2)
    
    #await playerManager()

    #threading.Thread(target=playerManager, daemon=True).start()
    #threading.Thread(target=sendProgress, daemon=True).start()