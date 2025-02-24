import bcrypt
from fastapi import APIRouter, HTTPException, Depends
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

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

    return JSONResponse(content={
        "username": user.username,
        "email": user.email
    })

@router.get("/units")
async def test_handler( 
        db: SessionLocal = Depends(get_db), 
        user: User = Depends(verify_token)
    ):
    
    unl = db.query(Unit).filter(
        Unit.owner_id==user.id or Unit.owner_mail==user.email
    ).all()

    return JSONResponse(content=[jsonObject(e) for e in unl])


