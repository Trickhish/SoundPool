from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse

from sqlalchemy import DateTime, Table, create_engine, Column, Integer, String, Boolean, Float, ForeignKey, select
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
    volume = Column(Float, default=1.0)                  # master volume (0..1)
    autoplay = Column(Boolean, default=False)            # keep playing similar tracks when the queue ends
    position_ms = Column(Float, default=0)               # persisted playback position (resume after restart)
    playing = Column(Boolean, default=False)             # was it playing when last saved
    party_active = Column(Boolean, default=False)        # guests may join via link
    party_code = Column(String(64), nullable=True)       # shareable join token
    voting_enabled = Column(Boolean, default=False)      # allow up/down-voting queued songs (auto-on with party mode)
    # Big-screen display mode (public read-only view via a shareable link)
    display_code = Column(String(64), nullable=True)     # shareable link token for the display page
    display_show_player = Column(Boolean, default=True)  # what the big screen shows
    display_show_lyrics = Column(Boolean, default=True)
    display_show_queue = Column(Boolean, default=True)   # upcoming songs
    display_show_skipvotes = Column(Boolean, default=True)  # skip-vote tally (only appears when someone has voted)
    display_show_qr = Column(Boolean, default=True)      # party join QR (only appears while a party is live)
    display_show_message = Column(Boolean, default=False)
    display_message = Column(String(512), nullable=True) # admin-authored message to show on screen
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    creation_date = Column(DateTime, default=datetime.utcnow)
    deezer_arl = Column(String(512), nullable=True)
    is_guest = Column(Boolean, default=False)            # accountless party guest

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
    location = Column(String(255), nullable=True)   # physical place (e.g. "Kitchen")
    online = Column(Boolean, nullable=False, default=False)
    owner_mail = Column(String(255), nullable=True)
    owner_id = Column(Integer, nullable=True)
    room_id = Column(Integer, nullable=True)             # room this unit is an output of (persisted attachment)
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
    # Fixed-preset role (owner|admin|member|guest); flags below are the source of
    # truth and may be overridden per-person on top of the role's preset.
    role = Column(String(16), default="guest")
    # Granular rights (admin implies all). Default (guest): add + vote_skip.
    can_add = Column(Boolean, default=True)
    can_remove = Column(Boolean, default=False)
    can_reorder = Column(Boolean, default=False)
    can_playpause = Column(Boolean, default=False)
    can_skip = Column(Boolean, default=False)
    can_vote_skip = Column(Boolean, default=True)
    can_vote = Column(Boolean, default=True)          # up/down-vote queued songs (on by default for everyone)
    can_seek = Column(Boolean, default=False)
    can_change_volume = Column(Boolean, default=False)
    can_manage_speakers = Column(Boolean, default=False)
    can_manage_party = Column(Boolean, default=False)
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