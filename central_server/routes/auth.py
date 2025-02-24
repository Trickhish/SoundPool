import bcrypt
from fastapi import APIRouter, HTTPException, Depends
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
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

def verify_token(
    x_token: str = Header(...),
    #session = Depends(get_db)
):
    try:
        session = SessionLocal()

        delete_expired_tokens()

        expiry_time = datetime.utcnow() - timedelta(hours=int(config["server"]["token_expiry_hours"]))

        token = session.query(Token).filter(
            Token.value == x_token,
            Token.creation_date > expiry_time
        ).first()

        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = session.query(User).filter(User.id == token.user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user
    
    except HTTPException as ex:
        raise ex
    except Exception as e:
        tb_str = traceback.format_exc()
        print(tb_str)
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")


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