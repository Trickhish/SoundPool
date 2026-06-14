import asyncio
import bcrypt
from fastapi import APIRouter, HTTPException, Depends, Query
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import JSONResponse

import tracks_manager as tmg

from db_models import *
from req_models import *
from database import *

from configuration import config
from routes.auth import verify_token

router = APIRouter()

@router.get("")
async def test_handler(request: LoginRequest, 
        db: SessionLocal = Depends(get_db), 
        user: User = Depends(verify_token)
    ):
    

    return JSONResponse(content="Valid token")

@router.get("/search")
async def search_handler(
        db: SessionLocal = Depends(get_db),
        user: User = Depends(verify_token),
        q: str = Query(..., description="Search query")
    ):
    if not user.deezer_arl:
        raise HTTPException(403, "Deezer account not connected")

    r = await asyncio.to_thread(tmg.search, q, user.deezer_arl)
    return JSONResponse(content=r)


