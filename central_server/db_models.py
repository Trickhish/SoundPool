from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse

from sqlalchemy import DateTime, Table, create_engine, Column, Integer, String, Boolean, ForeignKey, select
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

def jsonObject(inst):
    return({column.name: getattr(inst, column.name) for column in inst.__table__.columns})

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    password = Column(String(255), nullable=True)        # optional; public if null
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Persisted playback bookkeeping (live timeline is in-memory in room_player)
    current_index = Column(Integer, default=0)
    shuffle = Column(Boolean, default=False)
    repeat = Column(String(8), default="off")            # off | all | one
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    creation_date = Column(DateTime, default=datetime.utcnow)
    deezer_arl = Column(String(512), nullable=True)

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
    owner_mail = Column(String(255), nullable=True)
    owner_id = Column(Integer, nullable=True)
    status = Column(String(255), nullable=False, default="empty")
    # Possible values:
    # - "playing"     -> Actively playing media
    # - "paused"      -> Media loaded but currently paused
    # - "empty"       -> No media loaded
    # - "passthrough" -> Relaying external audio (no playback control)
    # - "idle"      -> Online but idle (not playing or paused)

class RoomTrack(Base):
    __tablename__ = "room_tracks"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), index=True, nullable=False)
    order = Column(Integer, default=0)          # position in the queue
    song_id = Column(String(64), nullable=False)
    title = Column(String(512), nullable=True)
    artist = Column(String(512), nullable=True)
    cover = Column(String(1024), nullable=True)
    duration_ms = Column(Integer, default=0)    # for the server timeline
    added_by = Column(Integer, nullable=True)

class RoomMember(Base):
    __tablename__ = "room_members"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    is_admin = Column(Boolean, default=False)
    # Granular rights (admin implies all). Default member: add + vote_skip.
    can_add = Column(Boolean, default=True)
    can_remove = Column(Boolean, default=False)
    can_reorder = Column(Boolean, default=False)
    can_playpause = Column(Boolean, default=False)
    can_skip = Column(Boolean, default=False)
    can_vote_skip = Column(Boolean, default=True)
    can_seek = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

class PlayHistory(Base):
    __tablename__ = "play_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    song_id = Column(String(64), nullable=True)
    title = Column(String(512), nullable=True)
    artist = Column(String(512), nullable=True)
    cover = Column(String(1024), nullable=True)
    played_at = Column(DateTime, default=datetime.utcnow)

class Favorite(Base):
    __tablename__ = "favorites"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    song_id = Column(String(64), nullable=False)
    title = Column(String(512), nullable=True)
    artist = Column(String(512), nullable=True)
    cover = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)