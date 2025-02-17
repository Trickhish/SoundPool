from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse

from sqlalchemy import DateTime, create_engine, Column, Integer, String, Boolean, ForeignKey, select
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from typing import List, Optional
from contextlib import asynccontextmanager
import os
from typing import List
from uuid import uuid4
import json
import asyncio

from database import Base

class Track(Base):
    __tablename__ = "tracks"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)

    room = relationship("Room", back_populates="tracks", foreign_keys=[room_id])

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=True)
    admin_id = Column(Integer, nullable=False)
    current_track_id = Column(Integer, ForeignKey("tracks.id"), nullable=True)
    votes_to_skip = Column(Integer, default=0)
    is_playing = Column(Boolean, default=False)
    
    tracks = relationship("Track", back_populates="room", foreign_keys=[Track.room_id])
    current_track = relationship("Track", backref="current_room", foreign_keys=[current_track_id])

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    email = Column(String, unique=True, nullable=True)
    creation_date = Column(DateTime, default=datetime.utcnow)

class Token(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    value = Column(String, unique=True, nullable=False)
    creation_date = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))