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
    # Fall back to the server's Deezer account so users without a connected
    # Deezer (party guests especially) can still search to add songs.
    arl = user.deezer_arl or config["deezer"]["cookie_arl"]
    if not arl:
        raise HTTPException(403, "Deezer account not connected")

    r = await asyncio.to_thread(tmg.search, q, arl)
    return JSONResponse(content=r)


@router.get("/suggestions")
async def suggestions_handler(
        db: SessionLocal = Depends(get_db),
        user: User = Depends(verify_token),
        seed: str = Query(None, description="Seed song id for a track radio"),
    ):
    # Songs to add for users without a library (party guests). If a seed song is
    # given, return a Deezer track-radio (similar to the seed / the party's vibe);
    # otherwise fall back to the popular chart. Uses the server ARL as a fallback.
    arl = user.deezer_arl or config["deezer"]["cookie_arl"]
    if not arl:
        return JSONResponse(content=[])
    if seed:
        r = await asyncio.to_thread(tmg.track_radio, arl, seed)
        if r:
            return JSONResponse(content=r)
    r = await asyncio.to_thread(tmg.chart, arl)
    return JSONResponse(content=r)


