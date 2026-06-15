import asyncio
import requests
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from db_models import *
from req_models import *
from database import *
from routes.auth import verify_token
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
                 "can_skip", "can_vote_skip", "can_seek"]


def rights_dict(member):
    if member is None:
        return None
    if member.is_admin:
        d = {f: True for f in RIGHTS_FIELDS}
        d["is_admin"] = True
        return d
    d = {f: bool(getattr(member, f)) for f in RIGHTS_FIELDS}
    d["is_admin"] = False
    return d


def get_member(db, room_id, user_id):
    return (db.query(RoomMember)
              .filter(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
              .first())


def room_dict(db, room, user):
    member = get_member(db, room.id, user.id)
    count = db.query(RoomMember).filter(RoomMember.room_id == room.id).count()
    return {
        "id": room.id,
        "name": room.name,
        "has_password": bool(room.password),
        "owner_id": room.owner_id,
        "member_count": count,
        "is_member": member is not None,
        "rights": rights_dict(member),
        "shuffle": room.shuffle,
        "repeat": room.repeat,
    }


@router.post("")
def create_room(body: RoomCreate,
                db: SessionLocal = Depends(get_db),  # type: ignore
                user: User = Depends(verify_token)):
    room = Room(name=body.name, password=body.password or None, owner_id=user.id)
    db.add(room)
    db.commit()
    db.refresh(room)
    db.add(RoomMember(room_id=room.id, user_id=user.id, is_admin=True,
                      can_add=True, can_remove=True, can_reorder=True,
                      can_playpause=True, can_skip=True, can_vote_skip=True, can_seek=True))
    db.commit()
    return JSONResponse(content=room_dict(db, room, user))


@router.get("")
def list_rooms(db: SessionLocal = Depends(get_db),  # type: ignore
               user: User = Depends(verify_token)):
    rooms = db.query(Room).order_by(Room.created_at.desc()).all()
    return JSONResponse(content=[room_dict(db, r, user) for r in rooms])


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
    await rp.add(track)
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


@router.post("/{room_id}/queue/move")
async def room_queue_move(room_id: int, body: QueueMoveRequest,
                          db: SessionLocal = Depends(get_db),  # type: ignore
                          user: User = Depends(verify_token)):
    _, rp = _require(db, room_id, user, "can_reorder")
    await rp.move(body.frm, body.to)
    room_player.persist_queue(room_id)
    return JSONResponse(content={"status": "ok"})


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
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    if get_member(db, room_id, user.id) is None:
        raise HTTPException(403, "Not a member of this room")
    unit = db.query(Unit).filter(Unit.id == body.unit_id).first()
    if not unit or unit.owner_id != user.id:
        raise HTTPException(403, "Not your unit")
    rp = room_player.ensure_loaded(room_id)
    await rp.attach(body.unit_id)
    return JSONResponse(content={"status": "attached"})


@router.post("/{room_id}/output/clear")
async def room_clear_output(room_id: int, body: OutputRequest,
                            db: SessionLocal = Depends(get_db),  # type: ignore
                            user: User = Depends(verify_token)):
    unit = db.query(Unit).filter(Unit.id == body.unit_id).first()
    if not unit or unit.owner_id != user.id:
        raise HTTPException(403, "Not your unit")
    rp = room_player.ensure_loaded(room_id)
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
    _, rp = _require(db, room_id, user, "can_playpause")
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
        db.add(RoomMember(room_id=room_id, user_id=user.id))  # default: add + vote_skip
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
    for f in RIGHTS_FIELDS + ["is_admin"]:
        val = getattr(body, f, None)
        if val is not None:
            setattr(target, f, val)
    db.commit()
    out = {"status": "ok"}
    out.update(rights_dict(target))
    return JSONResponse(content=out)
