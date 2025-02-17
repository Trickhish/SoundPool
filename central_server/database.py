from sqlalchemy import DateTime, create_engine, Column, Integer, String, Boolean, ForeignKey, select
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from db_models import *


DATABASE_URL = "sqlite:///./music_rooms.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

#async def get_async_session():
#    async with AsyncSessionLocal() as session:
#        yield session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()