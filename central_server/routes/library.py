from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import desc

from db_models import *
from req_models import *
from database import *
from routes.auth import verify_token

router = APIRouter()


@router.get("/history")
async def get_history(
    db: SessionLocal = Depends(get_db),  # type: ignore
    user: User = Depends(verify_token),
):
    rows = (db.query(PlayHistory)
              .filter(PlayHistory.user_id == user.id)
              .order_by(desc(PlayHistory.played_at))
              .limit(100).all())
    return JSONResponse(content=[{
        "id": r.song_id, "title": r.title, "artist": r.artist, "img_url": r.cover,
        "played_at": r.played_at.isoformat() if r.played_at else None,
    } for r in rows])


@router.get("/favorites")
async def get_favorites(
    db: SessionLocal = Depends(get_db),  # type: ignore
    user: User = Depends(verify_token),
):
    rows = (db.query(Favorite)
              .filter(Favorite.user_id == user.id)
              .order_by(desc(Favorite.created_at)).all())
    return JSONResponse(content=[{
        "id": r.song_id, "title": r.title, "artist": r.artist, "img_url": r.cover,
    } for r in rows])


@router.post("/favorites")
async def add_favorite(
    body: FavoriteRequest,
    db: SessionLocal = Depends(get_db),  # type: ignore
    user: User = Depends(verify_token),
):
    existing = (db.query(Favorite)
                  .filter(Favorite.user_id == user.id, Favorite.song_id == body.song_id)
                  .first())
    if not existing:
        db.add(Favorite(user_id=user.id, song_id=body.song_id,
                        title=body.title, artist=body.artist, cover=body.img_url))
        db.commit()
    return JSONResponse(content={"status": "ok"})


@router.delete("/favorites/{song_id}")
async def remove_favorite(
    song_id: str,
    db: SessionLocal = Depends(get_db),  # type: ignore
    user: User = Depends(verify_token),
):
    db.query(Favorite).filter(Favorite.user_id == user.id, Favorite.song_id == song_id).delete()
    db.commit()
    return JSONResponse(content={"status": "ok"})
