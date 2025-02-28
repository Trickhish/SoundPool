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