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
async def test_handler(request: LoginRequest, 
        db: SessionLocal = Depends(get_db), 
        user: User = Depends(verify_token)
    ):
    

    return JSONResponse(content="Valid token")

@router.get("/test")
async def test_handler(request: LoginRequest, 
        db: SessionLocal = Depends(get_db), 
        user: User = Depends(verify_token)
    ):
    

    return JSONResponse(content="Valid token")


