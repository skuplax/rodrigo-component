"""SQLAlchemy database models"""

from sqlalchemy import Column, String, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


class Source(Base):
    """Media source model (Spotify playlists, YouTube channels)"""
    
    __tablename__ = "sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50), nullable=False)  # 'spotify_playlist' or 'youtube_channel'
    name = Column(String(255), nullable=False)
    uri = Column(Text, nullable=False)
    source_type = Column(String(50), nullable=False, default='music')  # 'music' or 'news'
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class WatchedVideo(Base):
    """Watched YouTube video tracking"""
    
    __tablename__ = "watched_videos"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id = Column(String(50), nullable=False, unique=True)
    watched_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class AppState(Base):
    """Application state persistence"""
    
    __tablename__ = "app_state"
    
    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=False)  # Store as JSON for flexibility
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

