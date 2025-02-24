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
    name = Column(String(255), nullable=False)
    artist = Column(String(255), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)

    room = relationship("Room", back_populates="tracks", foreign_keys=[room_id])

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=True)
    admin_id = Column(Integer, nullable=False)
    current_track_id = Column(Integer, ForeignKey("tracks.id", use_alter=True, name="fk_rooms_current_track"), nullable=True)
    votes_to_skip = Column(Integer, default=0)
    is_playing = Column(Boolean, default=False)
    
    tracks = relationship("Track", back_populates="room", foreign_keys=[Track.room_id])
    current_track = relationship("Track", backref="current_room", foreign_keys=[current_track_id])

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id", name="fk_tracks_room"), nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    creation_date = Column(DateTime, default=datetime.utcnow)

class Token(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    value = Column(String(255), unique=True, nullable=False)
    creation_date = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))

class Unit(Base):
    __tablename__ = "units"
    id = Column(String(255), primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    online = Column(Boolean, nullable=False, default=False)
    status = Column(String(255), nullable=False, default="empty")
    # Possible values:
    # - "playing"     -> Actively playing media
    # - "paused"      -> Media loaded but currently paused
    # - "empty"       -> No media loaded
    # - "passthrough" -> Relaying external audio (no playback control)
    # - "idle"      -> Online but idle (not playing or paused)