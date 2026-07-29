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
from db_models import RoomTrack, Room, User, Unit

_rooms = {}          # room_id -> RoomPlayer
_loaded = set()      # room_ids whose queue has been loaded from the DB
_unit_room = {}      # unit_id -> room_id (a unit renders at most one room)


class RoomPlayer:
    def __init__(self, room_id):
        self.room_id = room_id
        self.queue = []            # list of {id,title,artist,cover,duration,uid,votes}
        self._seq = 0              # monotonic counter for per-track uids (vote targets)
        self.current_index = -1
        self.playing = False
        self.shuffle = False
        self.repeat = "off"        # off | all | one
        self.volume = 1.0          # master volume (scales each output's stream)
        self.autoplay = False      # append a Deezer track-radio when the queue runs low
        self._autoplay_busy = False
        self.voting_enabled = False  # room-level master switch for up/down-voting the queue
        self.base_offset = 0.0     # ms into the current track at _t0
        self._t0 = None            # monotonic timestamp the offset was anchored
        self.outputs = set()       # attached output unit ids
        self.arl = None            # room owner's Deezer ARL (for download data)
        self._dl_cache = {}        # song_id -> (song, url, key); holds current + prefetched next
        self._prefetching = set()  # song_ids currently being resolved (dedup)
        self._failed = set()       # song_ids that failed to resolve (unavailable) — skip them
        self._last_render = None   # (song_id, playing) last pushed to outputs
        self.votes = set()         # user ids who voted to skip the current track
        self.vote_threshold = 0    # votes needed to skip (updated on each vote)
        self._hb = 0               # heartbeat counter (conductor ticks)

    # ── queue votes (social-jukebox ordering) ──
    def _tag(self, track):
        """Give a queue track a stable uid + empty vote map (idempotent)."""
        if "uid" not in track:
            self._seq += 1
            track["uid"] = self._seq
        track.setdefault("votes", {})
        return track

    @staticmethod
    def _score(track):
        return sum((track.get("votes") or {}).values())

    def _resort_upcoming(self):
        """Hard-sort the upcoming songs by net vote score (highest first). Stable,
        so equal-score songs keep their current relative order (preserving both
        add order and any manual admin reordering within a tier). The current and
        already-played tracks are never moved."""
        start = self.current_index + 1 if self.current_index >= 0 else 0
        if start >= len(self.queue):
            return
        tail = self.queue[start:]
        tail.sort(key=lambda t: -self._score(t))
        self.queue[start:] = tail

    def _find_uid(self, uid):
        for i, t in enumerate(self.queue):
            if t.get("uid") == uid:
                return i
        return -1

    async def vote_track(self, uid, user_id, direction):
        """Register a member's up/down vote on an upcoming track and re-sort the
        queue by popularity. direction: +1 up, -1 down, 0 clears the vote."""
        idx = self._find_uid(uid)
        if idx < 0 or idx <= self.current_index:
            return   # gone, or already playing/played — can't reorder it
        votes = self.queue[idx].setdefault("votes", {})
        key = str(user_id)
        if direction == 0:
            votes.pop(key, None)
        else:
            votes[key] = 1 if direction > 0 else -1
        self._resort_upcoming()
        await self.broadcast()

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
            "autoplay": self.autoplay,
            "voting_enabled": self.voting_enabled,
            "queue": [{"key": i, "id": t["id"], "title": t["title"], "artist": t["artist"],
                       "cover": t["cover"], "duration": t["duration"], "ready": True, "failed": False,
                       "uid": t.get("uid"), "score": self._score(t)}
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
        self._prefetch_next()   # keep the upcoming track's download data warm

    async def _resolve_for(self, song_id):
        """Resolve (and cache) a song's Deezer download data, keyed by song id so
        the cache survives queue reordering."""
        if not song_id or not self.arl or song_id in self._failed:
            return None
        if song_id in self._dl_cache:
            return self._dl_cache[song_id]
        try:
            song = await asyncio.to_thread(tmg.get_song_gw_data, song_id, self.arl)
            song, url, _ext, key = await asyncio.to_thread(tmg.getDownloadData, song, self.arl)
        except Exception as e:
            print(f"[room_player] download-data resolve failed for {song_id}: {e}")
            self._failed.add(song_id)   # unavailable — don't keep retrying it
            return None
        self._dl_cache[song_id] = (song, url, key)
        return self._dl_cache[song_id]

    async def _ensure_playable(self):
        """Skip forward past tracks that can't be resolved (unavailable on
        Deezer) so one bad track doesn't silently stall the room. Bounded to the
        queue length; pauses if nothing is playable."""
        if not self.playing or not self.arl:
            return
        for _ in range(len(self.queue)):
            if self.cur() is None:
                break
            if await self._resolve_dl() is not None:
                return   # current track is playable
            bad = self.cur()
            print(f"[room_player] skipping unplayable track {bad.get('id')} — {bad.get('title')}")
            nxt = self.current_index + 1
            if nxt >= len(self.queue):
                if self.repeat == "all":
                    nxt = 0
                else:
                    break
            self._start_track(nxt)
        # nothing playable
        self.playing = False
        self._t0 = None

    async def _resolve_dl(self):
        """Resolve (and cache) the current track's Deezer download data."""
        cur = self.cur()
        return await self._resolve_for(cur["id"]) if cur else None

    def _prefetch_next(self):
        """Resolve the upcoming track's download data in the background so the
        next advance/skip is instant. Prunes the cache to current + next. Only
        useful for unit outputs (browser output resolves its own stream)."""
        if not self.outputs:
            self._dl_cache.clear()
            return
        cur = self.cur()
        keep = {cur["id"]} if cur else set()
        nxt = self._next_index(auto=True)
        if 0 <= nxt < len(self.queue):
            nid = self.queue[nxt]["id"]
            keep.add(nid)
            if nid not in self._dl_cache and nid not in self._prefetching:
                self._prefetching.add(nid)
                async def _run():
                    try:
                        await self._resolve_for(nid)
                    finally:
                        self._prefetching.discard(nid)
                asyncio.create_task(_run())
        for sid in list(self._dl_cache):
            if sid not in keep:
                del self._dl_cache[sid]

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
        _set_unit_room_db(unit_id, self.room_id)   # persist so it resurvives a restart
        await self._ensure_playable()   # if the current track is unavailable, skip to a playable one
        import pu_connection as puc
        u = puc.getUnitById(unit_id)
        cur = self.cur()
        if u and cur:
            dl = await self._resolve_dl()
            if dl:
                song, url, key = dl
                await u.send(["render", song, url, key, self.position(), self.playing, self.volume])
            else:
                await u.send(["stop"])
        await sse.triggerEvent(f"room_{self.room_id}", {**self.state(), "type": "state"})

    async def detach(self, unit_id):
        self.outputs.discard(unit_id)
        if _unit_room.get(unit_id) == self.room_id:
            _unit_room.pop(unit_id, None)
        _set_unit_room_db(unit_id, None)
        import pu_connection as puc
        u = puc.getUnitById(unit_id)
        if u:
            await u.send(["stop"])
        await sse.triggerEvent(f"room_{self.room_id}", {**self.state(), "type": "state"})

    # ── controls ──
    def _start_track(self, idx):
        self.current_index = idx
        self.base_offset = 0.0
        self._t0 = None      # clock stays at 0 until _dispatch_start anchors it
        self.votes = set()  # skip-votes are per-track

    async def _halt_outputs(self):
        """Immediately silence every output. Used when switching tracks so the
        previous song stops the moment you skip, rather than playing on while the
        next one downloads (which looks like the skip didn't register)."""
        if not self.outputs:
            return
        import pu_connection as puc
        for uid in list(self.outputs):
            u = puc.getUnitById(uid)
            if u:
                await u.send(["stop"])
        self._last_render = None   # force the next render to re-send

    async def _dispatch_start(self):
        """Render the freshly-started track, THEN start the clock. _start_track
        leaves _t0 unset so position() stays at 0 while the (possibly slow)
        download resolve + render is dispatched — otherwise the progress clock
        runs ahead of the audio and you get an 'advancing but silent' gap after
        jumping to an un-cached song. Outputs are halted first so the old track
        stops right away and playback pauses while the new one loads."""
        await self._ensure_playable()   # skip unplayable tracks so we don't stall
        await self._halt_outputs()
        await self.broadcast(force_render=True)
        if self.playing:
            self._t0 = time.monotonic()
        self._autoplay_topup()          # refill the queue with a radio if it's running low
        persist_position(self.room_id)  # capture the new current track

    async def play(self):
        if self.current_index < 0:
            if not self.queue:
                return
            self._start_track(0)
        if not self.playing:
            self.playing = True
            self._t0 = time.monotonic()  # resume from base_offset
        await self._ensure_playable()    # skip if the current track is unavailable
        await self.broadcast()
        if self.playing and self._t0 is None:  # re-anchor if _ensure_playable started a new track
            self._t0 = time.monotonic()

    async def pause(self):
        self.base_offset = self.position()
        self.playing = False
        self._t0 = None
        await self.broadcast()
        persist_position(self.room_id)   # capture where we paused

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
        # Playback always follows the (possibly shuffled) queue order, so the
        # displayed order is the play order — shuffling reorders the list once
        # rather than picking random tracks on the fly.
        if self.repeat == "one" and auto and self.current_index >= 0:
            return self.current_index
        if not self.queue:
            return -1
        nxt = self.current_index + 1
        if nxt >= len(self.queue):
            return 0 if self.repeat == "all" else -1
        return nxt

    async def shuffle_queue(self):
        """Randomize the queue order once. Keeps already-played + the currently
        playing track fixed and shuffles the upcoming songs; if nothing is
        playing, shuffles from the current slot (which may then hold a new
        track). Playback then proceeds in the new displayed order."""
        if len(self.queue) <= 1:
            await self.broadcast()
            return
        start = self.current_index + 1 if (self.playing and self.current_index >= 0) else max(self.current_index, 0)
        tail = self.queue[start:]
        random.shuffle(tail)
        self.queue[start:] = tail
        # cache is keyed by song id, so it survives the reorder (broadcast then
        # refreshes the prefetched "next" for the new order).
        await self.broadcast(force_render=True)

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
            await self.broadcast(force_render=True)
            return
        self._start_track(nxt)
        self.playing = True
        # _dispatch_start renders (incl. repeat-one, where the track id is
        # unchanged) then anchors the clock once audio is actually dispatched.
        await self._dispatch_start()

    async def prev(self):
        if self.shuffle:
            return await self.advance()
        if not self.queue:
            return
        self._start_track(0 if self.current_index <= 0 else self.current_index - 1)
        self.playing = True
        await self._dispatch_start()

    async def jump(self, idx):
        if 0 <= idx < len(self.queue):
            self._start_track(idx)
            self.playing = True
            await self._dispatch_start()

    async def add(self, track, autoplay=True, at_next=False):
        self._tag(track)
        if at_next and self.current_index >= 0:
            self.queue.insert(self.current_index + 1, track)  # play right after the current track
        else:
            self.queue.append(track)
            self._resort_upcoming()   # slot the new (unvoted) song into the score order
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

    async def set_autoplay(self, on):
        self.autoplay = bool(on)
        await self.broadcast()
        self._autoplay_topup()   # top up now if we're already near the end

    async def set_voting(self, on):
        self.voting_enabled = bool(on)
        await self.broadcast()   # push the new setting to every connected client

    # ── Autoplay: keep a track-radio flowing when the queue runs low ──
    def _autoplay_topup(self):
        """If autoplay is on and few tracks remain after the current one, fetch a
        Deezer track-radio (seeded from the current song) and append it, in the
        background so playback isn't blocked."""
        if not self.autoplay or self._autoplay_busy or not self.arl or self.repeat == "one":
            return
        cur = self.cur()
        upcoming = len(self.queue) - self.current_index - 1
        if cur is None or upcoming > 2:
            return
        self._autoplay_busy = True
        asyncio.create_task(self._do_autoplay_topup(cur["id"]))

    async def _do_autoplay_topup(self, seed_id):
        try:
            radio = await asyncio.to_thread(tmg.track_radio, self.arl, seed_id, 30)
            have = {t["id"] for t in self.queue}
            added = 0
            for r in radio:
                sid = str(r.get("id") or "")
                if not sid or sid in have or sid in self._failed:
                    continue
                self.queue.append(self._tag({
                    "id": sid, "title": r.get("title", ""), "artist": r.get("artist", ""),
                    "cover": r.get("img_url", ""), "duration": float(r.get("duration", 0)) * 1000.0,
                }))
                have.add(sid)
                added += 1
            if added:
                persist_queue(self.room_id)
                await self.broadcast()
        except Exception as e:
            print(f"[room_player] autoplay top-up failed: {e}")
        finally:
            self._autoplay_busy = False

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
        # Persist the position periodically so a restart resumes near where it was.
        if self.playing and self._hb % 15 == 0:
            persist_position(self.room_id)


async def on_unit_online(unit_id):
    """Reconcile a (re)connected unit with the conductor. If it's still an output
    of a live room, re-render so it resyncs; otherwise it's orphaned (e.g. the
    server restarted and lost the in-memory attachment) — tell it to stop instead
    of letting it keep playing a stale track the UI no longer controls."""
    import pu_connection as puc
    u = puc.getUnitById(unit_id)
    if u is None:
        return
    rid = _unit_room.get(unit_id)
    if rid is None:
        # Not attached in memory — check the persisted attachment (e.g. after a
        # server restart) and restore it so the unit resumes its room.
        rid = _unit_room_db(unit_id)
        if rid is not None:
            rp = ensure_loaded(rid)
            rp.outputs.add(unit_id)
            _unit_room[unit_id] = rid
    rp = _rooms.get(rid) if rid is not None else None
    if rp is not None and unit_id in rp.outputs and rp.cur() is not None:
        dl = await rp._resolve_dl()
        if dl:
            song, url, key = dl
            await u.send(["render", song, url, key, rp.position(), rp.playing, rp.volume])
            return
    await u.send(["stop"])


def _set_unit_room_db(unit_id, room_id):
    """Persist a unit's room attachment so it survives a server restart."""
    db = SessionLocal()
    try:
        u = db.query(Unit).filter(Unit.id == unit_id).first()
        if u:
            u.room_id = room_id
            db.commit()
    finally:
        db.close()


def _unit_room_db(unit_id):
    db = SessionLocal()
    try:
        u = db.query(Unit).filter(Unit.id == unit_id).first()
        return u.room_id if u else None
    finally:
        db.close()


def persist_position(room_id):
    """Lightweight save of playback position/state (no queue rewrite)."""
    room_id = int(room_id)
    rp = _rooms.get(room_id)
    if rp is None:
        return
    db = SessionLocal()
    try:
        room = db.query(Room).filter(Room.id == room_id).first()
        if room:
            room.position_ms = rp.position()
            room.playing = rp.playing
            room.current_index = rp.current_index
            db.commit()
    finally:
        db.close()


def get_player(room_id):
    room_id = int(room_id)  # one instance per room regardless of caller's type
    rp = _rooms.get(room_id)
    if rp is None:
        rp = RoomPlayer(room_id)
        _rooms[room_id] = rp
    return rp


def ensure_loaded(room_id):
    """Lazily load a room's persisted queue + flags from the DB once."""
    room_id = int(room_id)
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
            rp.autoplay = bool(getattr(room, "autoplay", False))
            rp.voting_enabled = bool(getattr(room, "voting_enabled", False))
            owner = db.query(User).filter(User.id == room.owner_id).first()
            rp.arl = owner.deezer_arl if owner else None
        tracks = (db.query(RoomTrack)
                    .filter(RoomTrack.room_id == room_id)
                    .order_by(RoomTrack.order).all())
        rp.queue = [rp._tag({"id": t.song_id, "title": t.title, "artist": t.artist,
                             "cover": t.cover, "duration": t.duration_ms}) for t in tracks]
        # Resume at the persisted position/playing state (so a restart continues
        # rather than resetting to the top, paused).
        if rp.queue:
            ci = room.current_index if room else 0
            rp.current_index = ci if (0 <= ci < len(rp.queue)) else 0
            rp.base_offset = float(getattr(room, "position_ms", 0) or 0)
            rp.playing = bool(getattr(room, "playing", False))
            rp._t0 = time.monotonic() if rp.playing else None
        # Restore persisted output attachments so the conductor knows its outputs
        # even before the units reconnect.
        for u in db.query(Unit).filter(Unit.room_id == room_id).all():
            rp.outputs.add(u.id)
            _unit_room[u.id] = room_id
    finally:
        db.close()
    _loaded.add(room_id)
    return rp


def persist_queue(room_id):
    """Write the in-memory queue + flags back to the DB."""
    room_id = int(room_id)
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
            room.autoplay = rp.autoplay
            room.voting_enabled = rp.voting_enabled
            room.position_ms = rp.position()
            room.playing = rp.playing
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


_conductor_started = False


async def conductor():
    """Single background loop that ticks every active room."""
    global _conductor_started
    if _conductor_started:
        return
    _conductor_started = True
    # Restore rooms that had units attached so playback resumes after a restart,
    # even before a client opens the room.
    try:
        db = SessionLocal()
        rids = {u.room_id for u in db.query(Unit).filter(Unit.room_id != None).all() if u.room_id}
        db.close()
        for rid in rids:
            try:
                ensure_loaded(rid)
                print(f"[room_player] restored room {rid} with persisted outputs")
            except Exception as e:
                print(f"[room_player] restore room {rid} failed: {e}")
    except Exception as e:
        print(f"[room_player] startup restore failed: {e}")
    while True:
        for rp in list(_rooms.values()):
            try:
                await rp.tick()
            except Exception as e:
                print(f"[room_player] tick error room {rp.room_id}: {e}")
        await asyncio.sleep(1)
