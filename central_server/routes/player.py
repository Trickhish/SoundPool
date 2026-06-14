import asyncio
import bcrypt
from fastapi import APIRouter, HTTPException, Depends
import jwt
from sqlalchemy import exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker, relationship, declarative_base

from fastapi.responses import JSONResponse

from db_models import *
from req_models import *
from database import *

from configuration import config
from routes.auth import verify_token

import pu_connection as puc
import tracks_manager as tmg

router = APIRouter()

@router.get("/{player_id}")
async def test_handler(
        player_id: str,
        db: SessionLocal = Depends(get_db),  # type: ignore
        user: User = Depends(verify_token)
    ):

    u:Unit = db.query(Unit).filter(Unit.id==player_id).first()
    if (u==None):
        raise HTTPException(404, "Player not found")
    
    if (u.owner_id != user.id):
        stmt = select(exists().where(
            room_rights.c.user_id == user.id,
            room_rights.c.room_id == player_id
        ))
        lnk = db.execute(stmt).scalar()

        if not lnk:
            raise HTTPException(401, "You're not allowed to view this player")

    return JSONResponse(content=jsonObject(u))

@router.post("/{player_id}/play")
async def play_handler(
    player_id: str,
    db: SessionLocal = Depends(get_db),  # type: ignore
    user: User = Depends(verify_token)
):
    u:Unit = db.query(Unit).filter(Unit.id==player_id).first()
    if (u==None):
        raise HTTPException(404, "Player not found")
    
    if (u.owner_id != user.id):
        raise HTTPException(401, "You do not have control rights over this player")
    

    uc = puc.getUnitById(u.id)
    if uc==None:
        raise HTTPException(503, "The player is offline")
    
    await uc.play()

    u.status = "playing"
    db.commit()
    db.refresh(u)

    return JSONResponse(content={"message": "started music"})

@router.post("/{player_id}/pause")
async def pause_handler(
    player_id: str,
    db: SessionLocal = Depends(get_db),  # type: ignore
    user: User = Depends(verify_token)
):
    u:Unit = db.query(Unit).filter(Unit.id==player_id).first()
    if (u==None):
        raise HTTPException(404, "Player not found")
    
    if (u.owner_id != user.id):
        raise HTTPException(401, "You do not have control rights over this player")
    
    uc = puc.getUnitById(u.id)
    if uc==None:
        raise HTTPException(503, "The player is offline")
    
    await uc.pause()

    u.status = "paused"
    db.commit()
    db.refresh(u)

    return JSONResponse(content={"message": "paused music"})

@router.post("/{player_id}/prev")
async def prev_handler(
    player_id: str,
    db: SessionLocal = Depends(get_db),  # type: ignore
    user: User = Depends(verify_token)
):
    u:Unit = db.query(Unit).filter(Unit.id==player_id).first()
    if (u==None):
        raise HTTPException(404, "Player not found")
    
    if (u.owner_id != user.id):
        raise HTTPException(401, "You do not have control rights over this player")
    
    uc = puc.getUnitById(u.id)
    if uc==None:
        raise HTTPException(503, "The player is offline")
    
    await uc.send(["control", "prev"])

    u.status = "loading"
    db.commit()
    db.refresh(u)

    return JSONResponse(content={"message": "loading previous song"})

@router.post("/{player_id}/next")
async def prev_handler(
    player_id: str,
    db: SessionLocal = Depends(get_db),  # type: ignore
    user: User = Depends(verify_token)
):
    u:Unit = db.query(Unit).filter(Unit.id==player_id).first()
    if (u==None):
        raise HTTPException(404, "Player not found")
    
    if (u.owner_id != user.id):
        raise HTTPException(401, "You do not have control rights over this player")
    
    uc = puc.getUnitById(u.id)
    if uc==None:
        raise HTTPException(503, "The player is offline")
    
    await uc.send(["control", "next"])

    u.status = "loading"
    db.commit()
    db.refresh(u)

    return JSONResponse(content={"message": "loading next song"})


@router.post("/{player_id}/queue/add")
async def queue_add(
    player_id: str,
    body: QueueAddRequest,
    db: SessionLocal = Depends(get_db),
    user: User = Depends(verify_token),
):
    u: Unit = db.query(Unit).filter(Unit.id == player_id).first()
    if not u:
        raise HTTPException(404, "Player not found")
    if u.owner_id != user.id:
        raise HTTPException(401, "Not your player")
    if not user.deezer_arl:
        raise HTTPException(403, "Deezer not connected")
    uc = puc.getUnitById(u.id)
    if not uc:
        raise HTTPException(503, "Player offline")

    song = await asyncio.to_thread(tmg.get_song_gw_data, body.song_id, user.deezer_arl)
    song_data, url, _ext, key = await asyncio.to_thread(tmg.getDownloadData, song, user.deezer_arl)
    await uc.send(["queue_add", song_data, url, key])
    return JSONResponse(content={"status": "queued"})


@router.delete("/{player_id}/queue/clear")
async def queue_clear(
    player_id: str,
    db: SessionLocal = Depends(get_db),
    user: User = Depends(verify_token),
):
    u: Unit = db.query(Unit).filter(Unit.id == player_id).first()
    if not u:
        raise HTTPException(404, "Player not found")
    if u.owner_id != user.id:
        raise HTTPException(401, "Not your player")
    uc = puc.getUnitById(u.id)
    if not uc:
        raise HTTPException(503, "Player offline")

    await uc.send(["control", "clear"])
    return JSONResponse(content={"status": "cleared"})


@router.post("/{player_id}/queue/playlist/{playlist_id}")
async def queue_playlist(
    player_id: str,
    playlist_id: int,
    db: SessionLocal = Depends(get_db),
    user: User = Depends(verify_token),
):
    u: Unit = db.query(Unit).filter(Unit.id == player_id).first()
    if not u:
        raise HTTPException(404, "Player not found")
    if u.owner_id != user.id:
        raise HTTPException(401, "Not your player")
    if not user.deezer_arl:
        raise HTTPException(403, "Deezer not connected")
    uc = puc.getUnitById(u.id)
    if not uc:
        raise HTTPException(503, "Player offline")

    tracks = await asyncio.to_thread(tmg.get_deezer_playlist_tracks_gw, playlist_id, user.deezer_arl)

    async def _enqueue():
        for track in tracks:
            try:
                song_data, url, _ext, key = await asyncio.to_thread(tmg.getDownloadData, track, user.deezer_arl)
                await uc.send(["queue_add", song_data, url, key])
            except Exception as e:
                print(f"[queue_playlist] skipped track: {e}")

    asyncio.create_task(_enqueue())
    return JSONResponse(content={"status": "queuing", "total": len(tracks)})