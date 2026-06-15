from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from db_models import *
from req_models import *
from database import *
from routes.auth import verify_token

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
    return JSONResponse(content=room_dict(db, room, user))


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
