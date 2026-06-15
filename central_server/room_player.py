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
import tracks_manager as tmg
from database import SessionLocal
from db_models import RoomTrack, Room, User

_rooms = {}          # room_id -> RoomPlayer
_loaded = set()      # room_ids whose queue has been loaded from the DB
_unit_room = {}      # unit_id -> room_id (a unit renders at most one room)


class RoomPlayer:
    def __init__(self, room_id):
        self.room_id = room_id
        self.queue = []            # list of {id,title,artist,cover,duration}
        self.current_index = -1
        self.playing = False
        self.shuffle = False
        self.repeat = "off"        # off | all | one
        self.volume = 1.0          # master volume (scales each output's stream)
        self.base_offset = 0.0     # ms into the current track at _t0
        self._t0 = None            # monotonic timestamp the offset was anchored
        self.outputs = set()       # attached output unit ids
        self.arl = None            # room owner's Deezer ARL (for download data)
        self._dl_index = -1        # which queue index _dl was resolved for
        self._dl = None            # cached (song, url, key) for the current track
        self._last_render = None   # (song_id, playing) last pushed to outputs
        self.votes = set()         # user ids who voted to skip the current track
        self.vote_threshold = 0    # votes needed to skip (updated on each vote)
        self._hb = 0               # heartbeat counter (conductor ticks)

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
            "volume": self.volume,
            "shuffle": self.shuffle,
            "repeat": self.repeat,
            "queue": [{"key": i, "id": t["id"], "title": t["title"], "artist": t["artist"],
                       "cover": t["cover"], "duration": t["duration"], "ready": True, "failed": False}
                      for i, t in enumerate(self.queue)],
            "outputs": sorted(self.outputs),
            "vote_count": len(self.votes),
            "vote_threshold": self.vote_threshold,
        }

    async def vote_skip(self, user_id, member_count):
        if self.cur() is None:
            return
        self.vote_threshold = max(1, (member_count + 1) // 2)  # simple majority
        self.votes.add(user_id)
        if len(self.votes) >= self.vote_threshold:
            await self.advance()  # _start_track clears votes
        else:
            await self.broadcast()

    async def broadcast(self, force_render=False):
        evt = dict(self.state())
        evt["type"] = "state"
        await sse.triggerEvent(f"room_{self.room_id}", evt)
        await self._render_outputs(force=force_render)

    async def _resolve_dl(self):
        """Resolve (and cache) the current track's Deezer download data."""
        if self._dl_index == self.current_index and self._dl is not None:
            return self._dl
        cur = self.cur()
        if cur is None or not self.arl:
            return None
        try:
            song = await asyncio.to_thread(tmg.get_song_gw_data, cur["id"], self.arl)
            song, url, _ext, key = await asyncio.to_thread(tmg.getDownloadData, song, self.arl)
        except Exception as e:
            print(f"[room_player] download-data resolve failed: {e}")
            return None
        self._dl = (song, url, key)
        self._dl_index = self.current_index
        return self._dl

    async def _render_outputs(self, force=False):
        if not self.outputs:
            return
        import pu_connection as puc
        cur = self.cur()
        if cur is None:
            if self._last_render is not None:
                for uid in list(self.outputs):
                    u = puc.getUnitById(uid)
                    if u:
                        await u.send(["stop"])
                self._last_render = None
            return
        sig = (cur["id"], self.playing)
        if not force and sig == self._last_render:
            return
        dl = await self._resolve_dl()
        if dl is None:
            return
        song, url, key = dl
        pos = self.position()
        for uid in list(self.outputs):
            u = puc.getUnitById(uid)
            if u:
                await u.send(["render", song, url, key, pos, self.playing, self.volume])
        self._last_render = sig

    async def attach(self, unit_id):
        # a unit renders at most one room
        prev = _unit_room.get(unit_id)
        if prev is not None and prev != self.room_id:
            other = _rooms.get(prev)
            if other:
                await other.detach(unit_id)
        _unit_room[unit_id] = self.room_id
        self.outputs.add(unit_id)
        import pu_connection as puc
        u = puc.getUnitById(unit_id)
        cur = self.cur()
        if u and cur:
            dl = await self._resolve_dl()
            if dl:
                song, url, key = dl
                await u.send(["render", song, url, key, self.position(), self.playing, self.volume])
        await sse.triggerEvent(f"room_{self.room_id}", {**self.state(), "type": "state"})

    async def detach(self, unit_id):
        self.outputs.discard(unit_id)
        if _unit_room.get(unit_id) == self.room_id:
            _unit_room.pop(unit_id, None)
        import pu_connection as puc
        u = puc.getUnitById(unit_id)
        if u:
            await u.send(["stop"])
        await sse.triggerEvent(f"room_{self.room_id}", {**self.state(), "type": "state"})

    # ── controls ──
    def _start_track(self, idx):
        self.current_index = idx
        self.base_offset = 0.0
        self._t0 = time.monotonic()
        self.votes = set()  # skip-votes are per-track

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
        await self.broadcast(force_render=True)

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
            # Queue exhausted (repeat off): reset to the first song, loaded but
            # paused, rather than going empty.
            self.playing = False
            self.current_index = 0 if self.queue else -1
            self.base_offset = 0.0
            self._t0 = None
            self.votes = set()
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
        if self.current_index < 0:
            # Load the first song (paused) so the room is never "empty" while
            # it has a queue — playback starts only if autoplay is requested.
            self.current_index = 0
            self.base_offset = 0.0
            self._t0 = None
            self.votes = set()
            if autoplay:
                self.playing = True
                self._t0 = time.monotonic()
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

    async def set_volume(self, level):
        self.volume = max(0.0, min(1.0, float(level)))
        await self.broadcast(force_render=True)  # push new stream volume to outputs

    async def tick(self):
        """Called ~1/s by the conductor loop."""
        self._hb += 1
        if self.playing and self.cur():
            pos = self.position()
            dur = self.cur()["duration"]
            if pos >= dur - 50:
                await self.advance(auto=True)
                return
            await sse.triggerEvent(f"room_{self.room_id}",
                                   {"type": "progress", "progress": pos, "duration": dur})
        # Periodic full-state heartbeat so any dropped state event (e.g. a
        # skip that didn't render) self-heals without a page reload.
        if self._hb % 5 == 0:
            await sse.triggerEvent(f"room_{self.room_id}", {**self.state(), "type": "state"})


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
            rp.volume = room.volume if room.volume is not None else 1.0
            owner = db.query(User).filter(User.id == room.owner_id).first()
            rp.arl = owner.deezer_arl if owner else None
        tracks = (db.query(RoomTrack)
                    .filter(RoomTrack.room_id == room_id)
                    .order_by(RoomTrack.order).all())
        rp.queue = [{"id": t.song_id, "title": t.title, "artist": t.artist,
                     "cover": t.cover, "duration": t.duration_ms} for t in tracks]
        # Load the first (or persisted) song, paused — never start empty.
        if rp.queue:
            ci = room.current_index if room else 0
            rp.current_index = ci if (0 <= ci < len(rp.queue)) else 0
            rp.playing = False
            rp.base_offset = 0.0
            rp._t0 = None
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
            room.volume = rp.volume
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
