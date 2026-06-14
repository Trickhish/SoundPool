import asyncio
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from db_models import *
from database import *
from routes.auth import verify_token
import deezer_smartlogin as sl

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


@router.delete("/logout")
async def deezer_logout(
    user: User = Depends(verify_token),
    db: SessionLocal = Depends(get_db),
):
    db_user: User = db.query(User).filter(User.id == user.id).first()
    db_user.deezer_arl = None
    db.commit()
    return JSONResponse(content={"status": "ok"})
