import asyncio
import secrets
import requests
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from db_models import *
from req_models import *
from database import *
from routes.auth import verify_token, create_access_token, hash_password
from configuration import config
import room_player
import tracks_manager as tmg
import deezer as dz


def _user_from_token(tokval):
    """Resolve a user from a raw token string (for <audio src> query auth)."""
    if not tokval:
        raise HTTPException(401, "Auth required")
    dbs = SessionLocal()
    try:
        expiry = datetime.utcnow() - timedelta(hours=int(config["server"]["token_expiry_hours"]))
        t = dbs.query(Token).filter(Token.value == tokval, Token.creation_date > expiry).first()
        if not t:
            raise HTTPException(403, "Unauthorized")
        return dbs.query(User).filter(User.id == t.user_id).first()
    finally:
        dbs.close()

router = APIRouter()

RIGHTS_FIELDS = ["can_add", "can_remove", "can_reorder", "can_playpause",
                 "can_skip", "can_vote_skip", "can_vote", "can_seek",
                 "can_change_volume", "can_manage_speakers", "can_manage_party"]

# Fixed role presets → flag values. Members can override individual flags on top.
# owner/admin are treated as all-true in rights_dict (is_admin short-circuit).
ROLE_PRESETS = {
    "owner":  {f: True for f in RIGHTS_FIELDS},
    "admin":  {f: True for f in RIGHTS_FIELDS},
    "member": {"can_add": True, "can_remove": True, "can_reorder": True,
               "can_playpause": True, "can_skip": True, "can_vote_skip": True,
               "can_vote": True, "can_seek": True, "can_change_volume": True,
               "can_manage_speakers": True, "can_manage_party": False},
    "guest":  {"can_add": True, "can_remove": False, "can_reorder": False,
               "can_playpause": False, "can_skip": False, "can_vote_skip": True,
               "can_vote": True, "can_seek": False, "can_change_volume": False,
               "can_manage_speakers": False, "can_manage_party": False},
}
# Roles whose holders can manage members / rights.
ADMIN_ROLES = ("owner", "admin")


def apply_role(member, role):
    """Stamp a role's preset flags onto a member row (source of truth = flags)."""
    preset = ROLE_PRESETS.get(role)
    if preset is None:
        return False
    member.role = role
    member.is_admin = role in ADMIN_ROLES
    for f, v in preset.items():
        setattr(member, f, v)
    return True


def rights_dict(member):
    if member is None:
        return None
    if member.is_admin:
        d = {f: True for f in RIGHTS_FIELDS}
        d["is_admin"] = True
        d["role"] = member.role or "admin"
        return d
    d = {f: bool(getattr(member, f)) for f in RIGHTS_FIELDS}
    d["is_admin"] = False
    d["role"] = member.role or "guest"
    return d


def get_member(db, room_id, user_id):
    return (db.query(RoomMember)
              .filter(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
              .first())


def room_dict(db, room, user):
    member = get_member(db, room.id, user.id)
    count = db.query(RoomMember).filter(RoomMember.room_id == room.id).count()
    rights = rights_dict(member)
    can_party = bool(rights and (rights.get("is_admin") or rights.get("can_manage_party")))
    is_admin_user = bool(rights and rights.get("is_admin"))
    return {
        "id": room.id,
        "name": room.name,
        "has_password": bool(room.password),
        "owner_id": room.owner_id,
        "member_count": count,
        "is_member": member is not None,
        "rights": rights,
        "shuffle": room.shuffle,
        "repeat": room.repeat,
        "party_active": bool(room.party_active),
        "voting_enabled": bool(room.voting_enabled),
        # the join code is only exposed to those who can manage the party
        "party_code": room.party_code if (can_party and room.party_active) else None,
        # display-mode config (link + settings shown only to admins)
        "display_code": room.display_code if is_admin_user else None,
        "display": {
            "show_player": bool(room.display_show_player),
            "show_lyrics": bool(room.display_show_lyrics),
            "show_queue": bool(room.display_show_queue),
            "show_qr": bool(room.display_show_qr),
            "show_message": bool(room.display_show_message),
            "message": room.display_message or "",
        } if is_admin_user else None,
    }


@router.post("")
def create_room(body: RoomCreate,
                db: SessionLocal = Depends(get_db),  # type: ignore
                user: User = Depends(verify_token)):
    if getattr(user, "is_guest", False):
        raise HTTPException(403, "Guests cannot create rooms")
    room = Room(name=body.name, password=body.password or None, owner_id=user.id)
    db.add(room)
    db.commit()
    db.refresh(room)
    owner_member = RoomMember(room_id=room.id, user_id=user.id)
    apply_role(owner_member, "owner")
    db.add(owner_member)
    db.commit()
    return JSONResponse(content=room_dict(db, room, user))


@router.get("")
def list_rooms(db: SessionLocal = Depends(get_db),  # type: ignore
               user: User = Depends(verify_token)):
    rooms = db.query(Room).order_by(Room.created_at.desc()).all()
    return JSONResponse(content=[room_dict(db, r, user) for r in rooms])


# ── Party guest access (public, no auth) ──
# Declared before "/{room_id}" so the literal "party" segment isn't captured by
# the int room_id path param.

@router.get("/party/{code}")
def party_info(code: str, db: SessionLocal = Depends(get_db)):  # type: ignore
    room = db.query(Room).filter(Room.party_code == code, Room.party_active == True).first()
    if not room:
        raise HTTPException(404, "Party not found or ended")
    count = db.query(RoomMember).filter(RoomMember.room_id == room.id).count()
    return JSONResponse(content={"room_id": room.id, "name": room.name, "member_count": count})


@router.post("/party/{code}/join")
def party_join(code: str, body: PartyJoinRequest,
               db: SessionLocal = Depends(get_db)):  # type: ignore
    room = db.query(Room).filter(Room.party_code == code, Room.party_active == True).first()
    if not room:
        raise HTTPException(404, "Party not found or ended")
    name = (body.username or "").strip()[:40] or "Guest"
    # Accountless guest: a throwaway user + token, joined as a guest member.
    guest = User(username=name, password=hash_password(secrets.token_urlsafe(16)),
                 email=None, is_guest=True)
    db.add(guest)
    db.commit()
    db.refresh(guest)
    token = create_access_token(guest.id)
    db.add(Token(value=token, user_id=guest.id, creation_date=datetime.utcnow()))
    member = RoomMember(room_id=room.id, user_id=guest.id)
    apply_role(member, "guest")
    db.add(member)
    db.commit()
    return JSONResponse(content={"token": token, "username": name,
                                 "room_id": room.id, "name": room.name})


# ── Big-screen display mode (public, no auth — access is via the display code) ──

_lyrics_cache = {}   # song_id -> {"synced": [...], "plain": str}


def _display_payload(db, room):
    rp = room_player.ensure_loaded(room.id)
    st = rp.state()
    q = st.get("queue") or []
    ci = st.get("current_index", -1)
    upcoming = q[ci + 1:] if ci >= 0 else q
    return {
        "room_id": room.id,
        "name": room.name,
        "party_active": bool(room.party_active),
        "party_code": room.party_code if room.party_active else None,
        "now_playing": st.get("now_playing"),
        "position": st.get("position", 0),
        "playing": st.get("playing", False),
        "queue": [{"title": t["title"], "artist": t["artist"], "cover": t["cover"]}
                  for t in upcoming[:12]],
        "show_player": bool(room.display_show_player),
        "show_lyrics": bool(room.display_show_lyrics),
        "show_queue": bool(room.display_show_queue),
        "show_qr": bool(room.display_show_qr),
        "show_message": bool(room.display_show_message),
        "message": room.display_message or "",
    }


@router.get("/display/{code}")
def display_info(code: str, db: SessionLocal = Depends(get_db)):  # type: ignore
    room = db.query(Room).filter(Room.display_code == code).first()
    if not room:
        raise HTTPException(404, "Display not found")
    return JSONResponse(content=_display_payload(db, room))


@router.post("/display/{code}/token")
def display_token(code: str, db: SessionLocal = Depends(get_db)):  # type: ignore
    """Mint a throwaway token so a public display can use the live SSE feed.
    The account is a non-member guest (no room membership, so it never affects
    member/vote counts). Reused per device via the browser's stored token."""
    room = db.query(Room).filter(Room.display_code == code).first()
    if not room:
        raise HTTPException(404, "Display not found")
    disp = User(username="display", password=hash_password(secrets.token_urlsafe(16)),
                email=None, is_guest=True)
    db.add(disp)
    db.commit()
    db.refresh(disp)
    token = create_access_token(disp.id)
    db.add(Token(value=token, user_id=disp.id, creation_date=datetime.utcnow()))
    db.commit()
    return JSONResponse(content={"token": token, "room_id": room.id})


@router.get("/display/{code}/lyrics/{song_id}")
def display_lyrics(code: str, song_id: str, db: SessionLocal = Depends(get_db)):  # type: ignore
    room = db.query(Room).filter(Room.display_code == code).first()
    if not room:
        raise HTTPException(404, "Display not found")

    def _cache(result, source):
        result = {**result, "source": source}
        if result["synced"] or result["plain"]:   # never pin an empty (transient) result
            _lyrics_cache[song_id] = result
            if len(_lyrics_cache) > 500:
                _lyrics_cache.pop(next(iter(_lyrics_cache)))
        return JSONResponse(content=result)

    cached = _lyrics_cache.get(song_id)
    # A Deezer hit is authoritative (correct version of the exact track), so it's
    # cached permanently. A cached *fallback* result is only provisional — it must
    # not shadow Deezer, so we re-check Deezer until it succeeds (multi-version
    # tracks otherwise risk an aggregator matching the wrong recording).
    if cached and cached.get("source") == "deezer":
        return JSONResponse(content=cached)

    owner = db.query(User).filter(User.id == room.owner_id).first()

    # 1) Deezer first (the source that knows the exact playing track).
    if owner and owner.deezer_arl:
        try:
            dz_lyr = tmg.get_song_lyrics(song_id, owner.deezer_arl)
        except Exception as e:
            print(f"[display] deezer lyrics failed for {song_id}: {e}")
            dz_lyr = {"synced": [], "plain": ""}
        if dz_lyr["synced"] or dz_lyr["plain"]:
            return _cache(dz_lyr, "deezer")

    # 2) Deezer had nothing — reuse a previously fetched fallback if we have one.
    if cached:
        return JSONResponse(content=cached)

    # 3) Otherwise fetch from the free aggregators (LRCLIB / Musixmatch / NetEase)
    #    using the queued track's title/artist (no extra Deezer call).
    t = (db.query(RoomTrack)
           .filter(RoomTrack.room_id == room.id, RoomTrack.song_id == song_id)
           .first())
    if t and t.title and t.artist:
        dur = (t.duration_ms or 0) / 1000.0 or None
        return _cache(tmg.get_fallback_lyrics(t.title, t.artist, dur), "fallback")
    return JSONResponse(content={"synced": [], "plain": ""})


@router.get("/{room_id}")
def get_room(room_id: int,
             db: SessionLocal = Depends(get_db),  # type: ignore
             user: User = Depends(verify_token)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    d = room_dict(db, room, user)
    d["state"] = room_player.ensure_loaded(room_id).state()
    return JSONResponse(content=d)


def _require(db, room_id, user, right):
    """Ensure the room exists and the user holds `right`; return the RoomPlayer."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    member = get_member(db, room_id, user.id)
    if member is None:
        raise HTTPException(403, "Not a member of this room")
    if not (member.is_admin or getattr(member, right, False)):
        raise HTTPException(403, f"Missing right: {right}")
    return room, room_player.ensure_loaded(room_id)


@router.post("/{room_id}/queue/add")
async def room_queue_add(room_id: int, body: QueueAddRequest,
                         db: SessionLocal = Depends(get_db),  # type: ignore
                         user: User = Depends(verify_token)):
    room, rp = _require(db, room_id, user, "can_add")
    owner = db.query(User).filter(User.id == room.owner_id).first()
    if not owner or not owner.deezer_arl:
        raise HTTPException(403, "Room owner has no Deezer account connected")
    gw = await asyncio.to_thread(tmg.get_song_gw_data, body.song_id, owner.deezer_arl)
    try:
        duration = float(gw.get("DURATION", 0)) * 1000.0
    except (TypeError, ValueError):
        duration = 0.0
    track = {"id": body.song_id, "title": body.title, "artist": body.artist,
             "cover": body.img_url or "", "duration": duration}
    await rp.add(track, at_next=body.at_next)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "queued"})


@router.post("/{room_id}/queue/playlist/{playlist_id}")
async def room_queue_playlist(room_id: int, playlist_id: int,
                              db: SessionLocal = Depends(get_db),  # type: ignore
                              user: User = Depends(verify_token)):
    room, rp = _require(db, room_id, user, "can_add")
    owner = db.query(User).filter(User.id == room.owner_id).first()
    if not owner or not owner.deezer_arl:
        raise HTTPException(403, "Room owner has no Deezer account connected")
    tracks = await asyncio.to_thread(tmg.get_deezer_playlist_tracks_gw, playlist_id, owner.deezer_arl)
    for t in tracks:
        pic = t.get("ALB_PICTURE", "")
        try:
            duration = float(t.get("DURATION", 0)) * 1000.0
        except (TypeError, ValueError):
            duration = 0.0
        await rp.add({
            "id": str(t.get("SNG_ID", "")), "title": t.get("SNG_TITLE", ""),
            "artist": t.get("ART_NAME", ""),
            "cover": f"https://e-cdns-images.dzcdn.net/images/cover/{pic}/250x250-000000-80-0-0.jpg" if pic else "",
            "duration": duration,
        }, autoplay=False)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "queuing", "total": len(tracks)})


@router.post("/{room_id}/queue/remove")
async def room_queue_remove(room_id: int, body: QueueIndexRequest,
                            db: SessionLocal = Depends(get_db),  # type: ignore
                            user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_remove")
    await rp.remove(body.index)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/queue/shuffle")
async def room_queue_shuffle(room_id: int,
                             db: SessionLocal = Depends(get_db),  # type: ignore
                             user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_reorder")
    await rp.shuffle_queue()
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/queue/move")
async def room_queue_move(room_id: int, body: QueueMoveRequest,
                          db: SessionLocal = Depends(get_db),  # type: ignore
                          user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_reorder")
    await rp.move(body.frm, body.to)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/queue/vote")
async def room_queue_vote(room_id: int, body: QueueVoteRequest,
                          db: SessionLocal = Depends(get_db),  # type: ignore
                          user: User = Depends(verify_token)):
    room, rp = _require(db, room_id, user, "can_vote")
    if not room.voting_enabled:
        raise HTTPException(403, "Voting is disabled in this room")
    await rp.vote_track(body.uid, user.id, body.direction)
    room_player.persist_queue(room_id)   # votes reorder the queue — persist the new order
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/voting")
async def room_set_voting(room_id: int, body: ShuffleRequest,
                          db: SessionLocal = Depends(get_db),  # type: ignore
                          user: User = Depends(verify_token)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    member = get_member(db, room_id, user.id)
    if member is None or not member.is_admin:
        raise HTTPException(403, "Only admins can change room settings")
    room.voting_enabled = bool(body.on)
    db.commit()
    await room_player.ensure_loaded(room_id).set_voting(body.on)
    return JSONResponse(content={"voting_enabled": bool(body.on)})


def _display_dict(room):
    return {
        "display_code": room.display_code,
        "show_player": bool(room.display_show_player),
        "show_lyrics": bool(room.display_show_lyrics),
        "show_queue": bool(room.display_show_queue),
        "show_qr": bool(room.display_show_qr),
        "show_message": bool(room.display_show_message),
        "message": room.display_message or "",
    }


def _require_admin(db, room_id, user):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    member = get_member(db, room_id, user.id)
    if member is None or not member.is_admin:
        raise HTTPException(403, "Only admins can change room settings")
    return room


@router.post("/{room_id}/display")
def enable_display(room_id: int,
                   db: SessionLocal = Depends(get_db),  # type: ignore
                   user: User = Depends(verify_token)):
    """Ensure the room has a display link (generates one on first use)."""
    room = _require_admin(db, room_id, user)
    if not room.display_code:
        room.display_code = secrets.token_urlsafe(9)
        db.commit()
    return JSONResponse(content=_display_dict(room))


@router.post("/{room_id}/display/config")
def set_display_config(room_id: int, body: DisplayConfigRequest,
                       db: SessionLocal = Depends(get_db),  # type: ignore
                       user: User = Depends(verify_token)):
    room = _require_admin(db, room_id, user)
    if not room.display_code:
        room.display_code = secrets.token_urlsafe(9)
    if body.show_player is not None:  room.display_show_player = body.show_player
    if body.show_lyrics is not None:  room.display_show_lyrics = body.show_lyrics
    if body.show_queue is not None:   room.display_show_queue = body.show_queue
    if body.show_qr is not None:      room.display_show_qr = body.show_qr
    if body.show_message is not None: room.display_show_message = body.show_message
    if body.message is not None:      room.display_message = body.message[:512]
    db.commit()
    return JSONResponse(content=_display_dict(room))


@router.post("/{room_id}/queue/jump")
async def room_queue_jump(room_id: int, body: QueueIndexRequest,
                          db: SessionLocal = Depends(get_db),  # type: ignore
                          user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_skip")
    await rp.jump(body.index)
    return JSONResponse(content={"status": "ok"})


@router.delete("/{room_id}/queue/clear")
async def room_queue_clear(room_id: int,
                           db: SessionLocal = Depends(get_db),  # type: ignore
                           user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_remove")
    await rp.clear()
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


@router.get("/{room_id}/song/{song_id}")
def room_song_stream(room_id: int, song_id: str, request: Request,
                     token: Optional[str] = None,
                     x_token: Optional[str] = Header(None),
                     db: SessionLocal = Depends(get_db)):  # type: ignore
    """Decrypted MP3 of a track for browser-output playback. Streams with
    HTTP Range support so the browser can start instantly and seek natively.
    Uses the room owner's Deezer account. Auth via x-token header or ?token=
    (so it works as an <audio src>)."""
    user = _user_from_token(token or x_token)
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    if get_member(db, room_id, user.id) is None:
        raise HTTPException(403, "Not a member of this room")
    owner = db.query(User).filter(User.id == room.owner_id).first()
    if not owner or not owner.deezer_arl:
        raise HTTPException(403, "Room owner has no Deezer account connected")
    song = tmg.get_song_gw_data(song_id, owner.deezer_arl)
    song, url, _ext, key = tmg.getDownloadData(song, owner.deezer_arl)

    # Total size (decrypt is 1:1) — from a 1-byte ranged probe.
    probe = requests.get(url, headers={"Range": "bytes=0-0"})
    total = None
    if probe.status_code == 206 and "Content-Range" in probe.headers:
        total = int(probe.headers["Content-Range"].split("/")[-1])
    if not total:
        total = int(probe.headers.get("Content-Length", 0)) or None

    # Parse a Range request (open-ended start- form).
    start = 0
    rng = request.headers.get("range") or request.headers.get("Range")
    if rng and rng.startswith("bytes="):
        try:
            start = int(rng.split("=", 1)[1].split("-", 1)[0] or 0)
        except ValueError:
            start = 0

    block0 = start // 2048           # aligned block containing `start`
    block_start = block0 * 2048
    skip = start - block_start       # bytes to drop from the first block

    def gen():
        with requests.get(url, headers={"Range": f"bytes={block_start}-"}, stream=True) as resp:
            i = block0
            buf = b""
            first = True
            for chunk in resp.iter_content(2048):
                if not chunk:
                    continue
                buf += chunk
                while len(buf) >= 2048:
                    block = buf[:2048]
                    buf = buf[2048:]
                    if i % 3 == 0:
                        block = dz.blowfishDecrypt(block, key)
                    i += 1
                    if first:
                        first = False
                        block = block[skip:]
                    yield block
            if buf:
                if first:
                    buf = buf[skip:]
                yield buf

    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    if start > 0 and total:
        headers["Content-Range"] = f"bytes {start}-{total-1}/{total}"
        headers["Content-Length"] = str(total - start)
        return StreamingResponse(gen(), status_code=206, media_type="audio/mpeg", headers=headers)
    if total:
        headers["Content-Length"] = str(total)
    return StreamingResponse(gen(), media_type="audio/mpeg", headers=headers)


@router.post("/{room_id}/output")
async def room_select_output(room_id: int, body: OutputRequest,
                             db: SessionLocal = Depends(get_db),  # type: ignore
                             user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_manage_speakers")
    unit = db.query(Unit).filter(Unit.id == body.unit_id).first()
    if not unit or unit.owner_id != user.id:
        raise HTTPException(403, "Not your unit")
    await rp.attach(body.unit_id)
    return JSONResponse(content={"status": "attached"})


@router.post("/{room_id}/output/clear")
async def room_clear_output(room_id: int, body: OutputRequest,
                            db: SessionLocal = Depends(get_db),  # type: ignore
                            user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_manage_speakers")
    unit = db.query(Unit).filter(Unit.id == body.unit_id).first()
    if not unit or unit.owner_id != user.id:
        raise HTTPException(403, "Not your unit")
    await rp.detach(body.unit_id)
    return JSONResponse(content={"status": "detached"})


@router.post("/{room_id}/play")
async def room_play(room_id: int,
                    db: SessionLocal = Depends(get_db),  # type: ignore
                    user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_playpause")
    await rp.play()
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/pause")
async def room_pause(room_id: int,
                     db: SessionLocal = Depends(get_db),  # type: ignore
                     user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_playpause")
    await rp.pause()
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/next")
async def room_next(room_id: int,
                    db: SessionLocal = Depends(get_db),  # type: ignore
                    user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_skip")
    await rp.advance()
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/prev")
async def room_prev(room_id: int,
                    db: SessionLocal = Depends(get_db),  # type: ignore
                    user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_skip")
    await rp.prev()
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/vote_skip")
async def room_vote_skip(room_id: int,
                         db: SessionLocal = Depends(get_db),  # type: ignore
                         user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_vote_skip")
    member_count = db.query(RoomMember).filter(RoomMember.room_id == room_id).count()
    await rp.vote_skip(user.id, member_count)
    return JSONResponse(content={"status": "ok", "votes": len(rp.votes), "threshold": rp.vote_threshold})


@router.post("/{room_id}/seek")
async def room_seek(room_id: int, body: SeekRequest,
                    db: SessionLocal = Depends(get_db),  # type: ignore
                    user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_seek")
    await rp.seek(body.percent)
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/volume")
async def room_volume(room_id: int, body: VolumeRequest,
                      db: SessionLocal = Depends(get_db),  # type: ignore
                      user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_change_volume")
    await rp.set_volume(body.level)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/shuffle")
async def room_shuffle(room_id: int, body: ShuffleRequest,
                       db: SessionLocal = Depends(get_db),  # type: ignore
                       user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_playpause")
    await rp.set_shuffle(body.on)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/repeat")
async def room_repeat(room_id: int, body: RepeatRequest,
                      db: SessionLocal = Depends(get_db),  # type: ignore
                      user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_playpause")
    await rp.set_repeat(body.mode)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/autoplay")
async def room_autoplay(room_id: int, body: ShuffleRequest,
                        db: SessionLocal = Depends(get_db),  # type: ignore
                        user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_playpause")
    await rp.set_autoplay(body.on)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


@router.post("/{room_id}/join")
def join_room(room_id: int, body: RoomJoinRequest,
              db: SessionLocal = Depends(get_db),  # type: ignore
              user: User = Depends(verify_token)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    if room.password and room.password != (body.password or ""):
        raise HTTPException(403, "Incorrect password")
    if get_member(db, room_id, user.id) is None:
        m = RoomMember(room_id=room_id, user_id=user.id)
        apply_role(m, "guest")  # default: add + vote_skip
        db.add(m)
        db.commit()
    return JSONResponse(content=room_dict(db, room, user))


@router.post("/{room_id}/leave")
def leave_room(room_id: int,
               db: SessionLocal = Depends(get_db),  # type: ignore
               user: User = Depends(verify_token)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    if room.owner_id == user.id:
        raise HTTPException(400, "The owner cannot leave their own room")
    db.query(RoomMember).filter(RoomMember.room_id == room_id, RoomMember.user_id == user.id).delete()
    db.commit()
    return JSONResponse(content={"status": "left"})


@router.post("/{room_id}/party")
async def start_party(room_id: int,
                      db: SessionLocal = Depends(get_db),  # type: ignore
                      user: User = Depends(verify_token)):
    room, rp = _require(db, room_id, user, "can_manage_party")
    if not room.party_code:
        room.party_code = secrets.token_urlsafe(9)
    room.party_active = True
    room.voting_enabled = True   # let guests vote by default during a party
    db.commit()
    await rp.set_voting(True)
    return JSONResponse(content={"party_active": True, "party_code": room.party_code,
                                 "voting_enabled": True})


@router.delete("/{room_id}/party")
async def stop_party(room_id: int,
                     db: SessionLocal = Depends(get_db),  # type: ignore
                     user: User = Depends(verify_token)):
    room, rp = _require(db, room_id, user, "can_manage_party")
    room.party_active = False
    room.party_code = None
    room.voting_enabled = False   # voting is party-scoped by default
    # Remove guest members and their throwaway accounts.
    guests = (db.query(RoomMember, User)
                .join(User, User.id == RoomMember.user_id)
                .filter(RoomMember.room_id == room_id, User.is_guest == True).all())
    for member, guest in guests:
        db.query(Token).filter(Token.user_id == guest.id).delete()
        db.delete(member)
        db.delete(guest)
    db.commit()
    await rp.set_voting(False)
    return JSONResponse(content={"party_active": False, "voting_enabled": False})


@router.delete("/{room_id}")
def delete_room(room_id: int,
                db: SessionLocal = Depends(get_db),  # type: ignore
                user: User = Depends(verify_token)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    if room.owner_id != user.id:
        raise HTTPException(403, "Only the owner can delete the room")
    db.query(RoomTrack).filter(RoomTrack.room_id == room_id).delete()
    db.query(RoomMember).filter(RoomMember.room_id == room_id).delete()
    db.query(Unit).filter(Unit.room_id == room_id).update({Unit.room_id: None})  # clear persisted attachments
    db.delete(room)
    db.commit()
    return JSONResponse(content={"status": "deleted"})


@router.get("/{room_id}/members")
def list_members(room_id: int,
                 db: SessionLocal = Depends(get_db),  # type: ignore
                 user: User = Depends(verify_token)):
    if get_member(db, room_id, user.id) is None:
        raise HTTPException(403, "Not a member of this room")
    members = db.query(RoomMember).filter(RoomMember.room_id == room_id).all()
    out = []
    for m in members:
        u = db.query(User).filter(User.id == m.user_id).first()
        entry = {"user_id": m.user_id, "username": u.username if u else "?"}
        entry.update(rights_dict(m))
        out.append(entry)
    return JSONResponse(content=out)


@router.post("/{room_id}/rights")
def set_rights(room_id: int, body: RoomRightsRequest,
               db: SessionLocal = Depends(get_db),  # type: ignore
               user: User = Depends(verify_token)):
    actor = get_member(db, room_id, user.id)
    if actor is None or not actor.is_admin:
        raise HTTPException(403, "Only admins can change rights")
    target = get_member(db, room_id, body.user_id)
    if target is None:
        raise HTTPException(404, "User is not a member of this room")
    room = db.query(Room).filter(Room.id == room_id).first()
    if target.user_id == room.owner_id:
        raise HTTPException(403, "The room owner's rights cannot be changed")

    # 1) Apply a role preset first (if given). "owner" is not assignable here.
    if body.role is not None:
        if body.role == "owner" or body.role not in ROLE_PRESETS:
            raise HTTPException(400, f"Invalid role: {body.role}")
        apply_role(target, body.role)

    # 2) Per-person overrides layered on top of the preset.
    for f in RIGHTS_FIELDS + ["is_admin"]:
        val = getattr(body, f, None)
        if val is not None:
            setattr(target, f, val)
    db.commit()
    out = {"status": "ok"}
    out.update(rights_dict(target))
    return JSONResponse(content=out)
