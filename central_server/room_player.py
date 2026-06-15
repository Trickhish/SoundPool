"""Server-side room player: the room is the playback authority ("conductor").

Each room owns a queue and a timeline (current track + position). A single
background loop ticks every room, advancing tracks when they end and emitting
`state`/`progress` over SSE on the `room_{id}` channel. Output units (Phase 3)
attach to a room and render whatever the room dictates.
"""
import asyncio
import time
import random

import sse
from database import SessionLocal
from db_models import RoomTrack, Room

_rooms = {}          # room_id -> RoomPlayer
_loaded = set()      # room_ids whose queue has been loaded from the DB


class RoomPlayer:
    def __init__(self, room_id):
        self.room_id = room_id
        self.queue = []            # list of {id,title,artist,cover,duration}
        self.current_index = -1
        self.playing = False
        self.shuffle = False
        self.repeat = "off"        # off | all | one
        self.base_offset = 0.0     # ms into the current track at _t0
        self._t0 = None            # monotonic timestamp the offset was anchored
        self.outputs = set()       # attached output unit ids (Phase 3)

    # ── timeline ──
    def position(self):
        if self.current_index < 0:
            return 0.0
        if not self.playing or self._t0 is None:
            return self.base_offset
        return self.base_offset + (time.monotonic() - self._t0) * 1000.0

    def cur(self):
        if 0 <= self.current_index < len(self.queue):
            return self.queue[self.current_index]
        return None

    def state(self):
        c = self.cur()
        return {
            "now_playing": ({"id": c["id"], "title": c["title"], "artist": c["artist"],
                             "album": c.get("album", ""), "cover": c["cover"],
                             "duration": c["duration"]} if c else None),
            "position": self.position(),
            "playing": self.playing,
            "current_index": self.current_index,
            "msid": (self.current_index + 1) if self.current_index >= 0 else 0,
            "volume": 1.0,
            "shuffle": self.shuffle,
            "repeat": self.repeat,
            "queue": [{"key": i, "id": t["id"], "title": t["title"], "artist": t["artist"],
                       "cover": t["cover"], "duration": t["duration"], "ready": True, "failed": False}
                      for i, t in enumerate(self.queue)],
        }

    async def broadcast(self):
        evt = dict(self.state())
        evt["type"] = "state"
        await sse.triggerEvent(f"room_{self.room_id}", evt)
        await self._render_outputs()

    async def _render_outputs(self):
        # Phase 3 fills this in (push render commands to attached output units).
        pass

    # ── controls ──
    def _start_track(self, idx):
        self.current_index = idx
        self.base_offset = 0.0
        self._t0 = time.monotonic()

    async def play(self):
        if self.current_index < 0:
            if not self.queue:
                return
            self._start_track(0)
        if not self.playing:
            self.playing = True
            self._t0 = time.monotonic()  # resume from base_offset
        await self.broadcast()

    async def pause(self):
        self.base_offset = self.position()
        self.playing = False
        self._t0 = None
        await self.broadcast()

    async def toggle(self):
        await (self.pause() if self.playing else self.play())

    async def seek(self, pct):
        c = self.cur()
        if not c:
            return
        self.base_offset = max(0.0, min(100.0, float(pct))) / 100.0 * c["duration"]
        self._t0 = time.monotonic()
        self.playing = True
        await self.broadcast()

    def _next_index(self, auto):
        if self.repeat == "one" and auto and self.current_index >= 0:
            return self.current_index
        if not self.queue:
            return -1
        if self.shuffle:
            if len(self.queue) == 1:
                return 0
            nxt = self.current_index
            while nxt == self.current_index:
                nxt = random.randrange(len(self.queue))
            return nxt
        nxt = self.current_index + 1
        if nxt >= len(self.queue):
            return 0 if self.repeat == "all" else -1
        return nxt

    async def advance(self, auto=False):
        nxt = self._next_index(auto)
        if nxt < 0:
            self.playing = False
            self.current_index = -1
            self.base_offset = 0.0
            self._t0 = None
        else:
            self._start_track(nxt)
            self.playing = True
        await self.broadcast()

    async def prev(self):
        if self.shuffle:
            return await self.advance()
        if self.current_index <= 0:
            self.base_offset = 0.0
            self._t0 = time.monotonic()
        else:
            self._start_track(self.current_index - 1)
        self.playing = True
        await self.broadcast()

    async def jump(self, idx):
        if 0 <= idx < len(self.queue):
            self._start_track(idx)
            self.playing = True
            await self.broadcast()

    async def add(self, track, autoplay=True):
        self.queue.append(track)
        if autoplay and self.current_index < 0 and not self.playing:
            self._start_track(len(self.queue) - 1)
            self.playing = True
        await self.broadcast()

    async def remove(self, idx):
        if not (0 <= idx < len(self.queue)):
            return
        del self.queue[idx]
        if idx < self.current_index:
            self.current_index -= 1
        elif idx == self.current_index:
            # removed the current track; stay at this slot (next song slides in)
            if self.current_index >= len(self.queue):
                self.current_index = -1
                self.playing = False
            else:
                self._start_track(self.current_index)
        await self.broadcast()

    async def move(self, frm, to):
        if not (0 <= frm < len(self.queue)):
            return
        item = self.queue.pop(frm)
        if frm < to:
            to -= 1
        to = max(0, min(to, len(self.queue)))
        self.queue.insert(to, item)
        # keep current pointer on the same track
        if frm == self.current_index:
            self.current_index = to
        elif frm < self.current_index <= to:
            self.current_index -= 1
        elif to <= self.current_index < frm:
            self.current_index += 1
        await self.broadcast()

    async def clear(self):
        self.queue = []
        self.current_index = -1
        self.playing = False
        self.base_offset = 0.0
        self._t0 = None
        await self.broadcast()

    async def set_shuffle(self, on):
        self.shuffle = bool(on)
        await self.broadcast()

    async def set_repeat(self, mode):
        if mode in ("off", "all", "one"):
            self.repeat = mode
        await self.broadcast()

    async def tick(self):
        """Called ~1/s by the conductor loop."""
        if self.playing and self.cur():
            pos = self.position()
            dur = self.cur()["duration"]
            if pos >= dur - 50:
                await self.advance(auto=True)
            else:
                await sse.triggerEvent(f"room_{self.room_id}",
                                       {"type": "progress", "progress": pos, "duration": dur})


def get_player(room_id):
    rp = _rooms.get(room_id)
    if rp is None:
        rp = RoomPlayer(room_id)
        _rooms[room_id] = rp
    return rp


def ensure_loaded(room_id):
    """Lazily load a room's persisted queue + flags from the DB once."""
    if room_id in _loaded:
        return get_player(room_id)
    rp = get_player(room_id)
    db = SessionLocal()
    try:
        room = db.query(Room).filter(Room.id == room_id).first()
        if room:
            rp.shuffle = bool(room.shuffle)
            rp.repeat = room.repeat or "off"
        tracks = (db.query(RoomTrack)
                    .filter(RoomTrack.room_id == room_id)
                    .order_by(RoomTrack.order).all())
        rp.queue = [{"id": t.song_id, "title": t.title, "artist": t.artist,
                     "cover": t.cover, "duration": t.duration_ms} for t in tracks]
    finally:
        db.close()
    _loaded.add(room_id)
    return rp


def persist_queue(room_id):
    """Write the in-memory queue + flags back to the DB."""
    rp = get_player(room_id)
    db = SessionLocal()
    try:
        db.query(RoomTrack).filter(RoomTrack.room_id == room_id).delete()
        for i, t in enumerate(rp.queue):
            db.add(RoomTrack(room_id=room_id, order=i, song_id=t["id"], title=t["title"],
                             artist=t["artist"], cover=t["cover"], duration_ms=int(t["duration"])))
        room = db.query(Room).filter(Room.id == room_id).first()
        if room:
            room.shuffle = rp.shuffle
            room.repeat = rp.repeat
            room.current_index = rp.current_index
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


async def conductor():
    """Single background loop that ticks every active room."""
    while True:
        for rp in list(_rooms.values()):
            try:
                await rp.tick()
            except Exception as e:
                print(f"[room_player] tick error room {rp.room_id}: {e}")
        await asyncio.sleep(1)
