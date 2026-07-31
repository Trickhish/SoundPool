import bcrypt
from fastapi import APIRouter, HTTPException, Depends, Request
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
import traceback

from db_models import *
from req_models import *
from database import *

from configuration import config

router = APIRouter()

async def fverify_token(
    x_token: str = Header(...),):
    #session: AsyncSession = Depends(get_async_session)):
    try:
        expiry_time = datetime.utcnow() - timedelta(hours=config["server"]["token_expiry_hours"])
        
        result = await session.execute(
            select(Token).where(
                Token.value == x_token,
                Token.creation_date > expiry_time
            )
        )
        token = result.scalars().first()

        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")

        result = await session.execute(select(User).where(User.id == token.user_id))
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return(user)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")

def delete_expired_tokens():
    session = SessionLocal()

    expiry_time = datetime.utcnow() - timedelta(hours=int(config["server"]["token_expiry_hours"]))
    session.query(Token).filter(Token.creation_date < expiry_time).delete()
    session.commit()
    session.close()

def verify_token(
    x_token: str = Header(...),
):
    try:
        session:Session = SessionLocal()
        delete_expired_tokens()

        expiry_time = datetime.utcnow() - timedelta(hours=int(config["server"]["token_expiry_hours"]))

        token = session.query(Token).filter(
            Token.value == x_token,
            Token.creation_date > expiry_time
        ).first()

        if not token:
            # 401 = not authenticated (client should log out). Distinct from 403
            # = authenticated but forbidden action (client should NOT log out).
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = session.query(User).filter(User.id == token.user_id).first()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user

    except HTTPException as ex:
        raise ex
    except Exception as e:
        tb_str = traceback.format_exc()
        print(tb_str)
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")
    finally:
        session.close()


def hash_password(password: str) -> str:
    return(bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return(bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8")))

def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=int(config["server"]["token_expiry_hours"]))
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, config["server"]["jwt_secret_key"], algorithm=config["server"]["jwt_algorithm"])

@router.get("/vtk")
async def vtk_handler(user: User = Depends(verify_token)):
    return(JSONResponse(content="Token is valid"))

@router.post("/login")
async def login_handler(request: LoginRequest, 
    db: SessionLocal = Depends(get_db),
    ):

    user:User = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token_value = create_access_token(user.id)

    new_token = Token(value=token_value, user_id=user.id, creation_date=datetime.utcnow())

    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    return JSONResponse(content={"token": token_value, "username": user.username})


@router.post("/register")
async def register_handler(req: RegisterRequest, 
    db: SessionLocal = Depends(get_db),
    ):

    user = db.query(User).filter(User.email == req.email).first()
    if user:
        raise HTTPException(status_code=401, detail="Email already used")
    
    hashed = hash_password(req.password)

    new_user = User(username=req.username, email=req.email, password=hashed)

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        token = create_access_token(new_user.id)
        new_token = Token(value=token, user_id=new_user.id, creation_date=datetime.utcnow())
        db.add(new_token)
        db.commit()
        db.refresh(new_token)

        return JSONResponse(content={"message": "User registered successfully", "token": token})

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# ── Device-code sign-in (TV / set-top boxes) ──────────────────────────────
# A D-pad and an on-screen keyboard make typing a password miserable, and it
# puts the password on a screen everyone in the room can see. Instead the
# device shows a short code, the user approves it from an already-signed-in
# browser, and the device polls until a token appears.
#
# In-memory on purpose: the server is single-worker (the room conductor keeps
# its state here too), and these entries live for minutes. A restart just means
# re-showing the code; the token it produces is a normal DB row.

import secrets as _secrets

DEVICE_CODE_TTL = timedelta(minutes=10)
_device_codes = {}          # user_code -> {device_code, user_id, created}
_device_attempts = {}       # ip -> [timestamps]

# No I/O/0/1 — they're the characters people misread off a TV across a room.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _prune_device_codes():
    now = datetime.utcnow()
    for k in [k for k, v in _device_codes.items() if now - v["created"] > DEVICE_CODE_TTL]:
        _device_codes.pop(k, None)


@router.post("/device/start")
async def device_start():
    """Called by the device. Returns the code to display and a secret to poll with."""
    _prune_device_codes()
    if len(_device_codes) > 500:
        raise HTTPException(503, "Too many pending sign-ins, try again shortly")
    for _ in range(20):
        user_code = "".join(_secrets.choice(_CODE_ALPHABET) for _ in range(6))
        if user_code not in _device_codes:
            break
    else:
        raise HTTPException(503, "Could not allocate a code")
    device_code = _secrets.token_urlsafe(32)
    _device_codes[user_code] = {"device_code": device_code, "user_id": None,
                                "created": datetime.utcnow()}
    return JSONResponse(content={
        "user_code": user_code,
        "device_code": device_code,
        "expires_in": int(DEVICE_CODE_TTL.total_seconds()),
    })


@router.get("/device/poll")
async def device_poll(device_code: str, db: SessionLocal = Depends(get_db)):  # type: ignore
    """Called by the device every few seconds until the user approves."""
    _prune_device_codes()
    entry = next((e for e in _device_codes.values() if e["device_code"] == device_code), None)
    if entry is None:
        raise HTTPException(410, "This code has expired — start again")
    if entry["user_id"] is None:
        return JSONResponse(content={"status": "pending"})

    user: User = db.query(User).filter(User.id == entry["user_id"]).first()
    if not user:
        raise HTTPException(410, "This code has expired — start again")
    token_value = create_access_token(user.id)
    db.add(Token(value=token_value, user_id=user.id, creation_date=datetime.utcnow()))
    db.commit()
    # Single use: the token is issued exactly once per approved code.
    _device_codes.pop(next(k for k, v in _device_codes.items() if v is entry), None)
    return JSONResponse(content={"status": "approved", "token": token_value,
                                 "username": user.username, "email": user.email})


@router.post("/device/approve")
async def device_approve(body: DeviceApproveRequest, request: Request,
                         user: User = Depends(verify_token)):
    """Called from a signed-in browser to hand this account to the device."""
    ip = request.client.host if request.client else "?"
    now = datetime.utcnow().timestamp()
    hits = [t for t in _device_attempts.get(ip, []) if now - t < 60]
    hits.append(now)
    _device_attempts[ip] = hits
    if len(_device_attempts) > 5000:
        for k in [k for k, v in _device_attempts.items() if not v or now - v[-1] > 60]:
            _device_attempts.pop(k, None)
    if len(hits) > 10:
        raise HTTPException(429, "Too many attempts — wait a minute and try again.")

    _prune_device_codes()
    code = (body.user_code or "").strip().upper().replace("-", "").replace(" ", "")
    entry = _device_codes.get(code)
    if entry is None:
        raise HTTPException(404, "That code isn't valid (or has expired).")
    if entry["user_id"] is not None:
        raise HTTPException(409, "That code has already been used.")
    entry["user_id"] = user.id
    return JSONResponse(content={"status": "ok"})
