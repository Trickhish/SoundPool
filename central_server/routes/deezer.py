import asyncio
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from db_models import *
from database import *
from routes.auth import verify_token
import deezer_smartlogin as sl
import tracks_manager as tmg

router = APIRouter()

# Pending smart-login sessions keyed by user id
_pending: dict = {}


@router.get("/status")
async def deezer_status(user: User = Depends(verify_token)):
    return JSONResponse(content={"connected": bool(user.deezer_arl)})


@router.post("/login/start")
async def deezer_login_start(user: User = Depends(verify_token)):
    info = await asyncio.to_thread(sl.start)
    qr_hash = info.get("qr_hash")
    _pending[user.id] = {"jwt": info["jwt"], "sid": info["sid"], "code": info["code"]}
    return JSONResponse(content={
        "code": info["code"],
        "journey_url": info["journey_url"],
        "ttl": info["ttl"],
        "poll_interval": info["poll_interval"],
        "qr_url": f"https://cdn-images.dzcdn.net/images/misc/{qr_hash}/500x500.png" if qr_hash else None,
    })


@router.get("/login/poll")
async def deezer_login_poll(
    user: User = Depends(verify_token),
    db: SessionLocal = Depends(get_db),
):
    pending = _pending.get(user.id)
    if not pending:
        raise HTTPException(400, "No pending Deezer login for this user")

    arl = await asyncio.to_thread(sl.poll, pending["jwt"], pending["sid"], pending["code"])
    if arl is None:
        return JSONResponse(content={"status": "pending"})

    db_user: User = db.query(User).filter(User.id == user.id).first()
    db_user.deezer_arl = arl
    db.commit()
    del _pending[user.id]
    return JSONResponse(content={"status": "ok"})


@router.get("/playlists")
async def deezer_playlists(user: User = Depends(verify_token)):
    if not user.deezer_arl:
        raise HTTPException(403, "Deezer not connected")
    playlists = await asyncio.to_thread(tmg.get_deezer_playlists, user.deezer_arl)
    return JSONResponse(content={"playlists": playlists})


@router.get("/playlist/{playlist_id}/tracks")
async def deezer_playlist_tracks(playlist_id: int, user: User = Depends(verify_token)):
    if not user.deezer_arl:
        raise HTTPException(403, "Deezer not connected")
    tracks = await asyncio.to_thread(tmg.get_deezer_playlist_tracks_gw, playlist_id, user.deezer_arl)
    out = []
    for t in tracks:
        pic = t.get("ALB_PICTURE", "")
        out.append({
            "id": str(t.get("SNG_ID", "")),
            "title": t.get("SNG_TITLE", ""),
            "artist": t.get("ART_NAME", ""),
            "img_url": f"https://e-cdns-images.dzcdn.net/images/cover/{pic}/250x250-000000-80-0-0.jpg" if pic else "",
        })
    return JSONResponse(content={"tracks": out})


@router.delete("/logout")
async def deezer_logout(
    user: User = Depends(verify_token),
    db: SessionLocal = Depends(get_db),
):
    db_user: User = db.query(User).filter(User.id == user.id).first()
    db_user.deezer_arl = None
    db.commit()
    return JSONResponse(content={"status": "ok"})
