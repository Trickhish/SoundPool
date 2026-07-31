import bcrypt
from fastapi import APIRouter, HTTPException, Depends
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_

from fastapi.responses import JSONResponse

from db_models import *
from req_models import *
from database import *

from configuration import config
from routes.auth import verify_token

router = APIRouter()

@router.get("")
async def test_handler( 
        db: SessionLocal = Depends(get_db), 
        user: User = Depends(verify_token)
    ):

    # Include the linked Deezer profile (name + avatar) so clients can show it.
    # Best-effort: never fail the whole call if Deezer is unreachable.
    deezer = {"name": "", "picture": ""}
    if getattr(user, "deezer_arl", None):
        try:
            import tracks_manager as tmg
            deezer = tmg.get_deezer_profile(user.deezer_arl)
        except Exception as e:
            print(f"[user] deezer profile failed: {e}")

    return JSONResponse(content={
        "username": user.username,
        "email": user.email,
        "is_guest": bool(getattr(user, "is_guest", False)),
        "deezer_name": deezer["name"],
        "deezer_picture": deezer["picture"],
    })

@router.get("/units")
async def test_handler( 
        db: SessionLocal = Depends(get_db), 
        user: User = Depends(verify_token)
    ):
    
    unl = db.query(Unit).filter(
        or_(Unit.owner_id == user.id, Unit.owner_mail == user.email)
    ).all()

    return JSONResponse(content=[jsonObject(e) for e in unl])


