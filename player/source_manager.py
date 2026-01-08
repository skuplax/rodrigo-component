"""Source manager for YouTube channels and Spotify playlists"""

from typing import List, Optional
from dataclasses import dataclass
from enum import Enum
import logging
import json
from pathlib import Path

from db.models import Source as SourceModel, AppState as AppStateModel
from db.database import get_sync_session

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Type of media source"""
    SPOTIFY_PLAYLIST = "spotify_playlist"
    YOUTUBE_CHANNEL = "youtube_channel"


@dataclass
class MediaSource:
    """Represents a media source (YouTube channel or Spotify playlist)"""
    type: SourceType
    name: str  # Human-readable name
    uri: str  # Channel URL or playlist URI
    source_type: str = "music"  # Category: "music" or "news"


class SourceManager:
    """Manages list of sources and cycling through them"""
    
    def __init__(self, sources: Optional[List[MediaSource]] = None, config_path: Optional[Path] = None):
        """
        Initialize source manager.
        
        Args:
            sources: List of media sources. If None, loads from database first, then file
            config_path: Path to sources.json file for fallback
        """
        if sources is not None:
            self.sources: List[MediaSource] = sources
            self.current_source_index = 0
        else:
            # Load from database, fallback to file
            self.sources, self.current_source_index = self._load_sources()
        
        # Validate index is within bounds
        if self.sources and self.current_source_index >= len(self.sources):
            logger.warning(f"Current source index {self.current_source_index} out of bounds, resetting to 0")
            self.current_source_index = 0
        
        logger.info(f"SourceManager initialized with {len(self.sources)} sources (current index: {self.current_source_index})")
    
    def _load_sources(self) -> tuple[List[MediaSource], int]:
        """Load sources from database, fallback to file"""
        try:
            sources = self._load_sources_from_db()
            if sources:
                logger.info(f"Loaded {len(sources)} sources from database")
                current_index = self._load_current_index_from_db()
                return sources, current_index
        except Exception as e:
            logger.warning(f"Failed to load sources from database: {e}")
        
        # Fallback to file
        sources = self._load_sources_from_file()
        return sources, 0
    
    def _load_sources_from_db(self) -> List[MediaSource]:
        """Load sources from database using sync session"""
        from sqlalchemy import select
        
        with get_sync_session() as session:
            result = session.execute(select(SourceModel))
            db_sources = result.scalars().all()
            
            sources = []
            for db_source in db_sources:
                try:
                    source_type = SourceType(db_source.type)
                    sources.append(MediaSource(
                        type=source_type,
                        name=db_source.name,
                        uri=db_source.uri,
                        source_type=db_source.source_type
                    ))
                except (ValueError, AttributeError) as e:
                    logger.error(f"Invalid source in database: {db_source}, error: {e}")
                    continue
            
            return sources
    
    def _load_current_index_from_db(self) -> int:
        """Load current source index from database using sync session"""
        from sqlalchemy import select
        
        with get_sync_session() as session:
            result = session.execute(
                select(AppStateModel).where(AppStateModel.key == 'current_source_index')
            )
            app_state = result.scalar_one_or_none()
            
            if app_state and app_state.value:
                try:
                    return max(0, int(app_state.value))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid current_source_index value: {app_state.value}")
            return 0
    
    def _load_sources_from_file(self, config_path: Optional[Path] = None) -> List[MediaSource]:
        """Load sources from JSON config file"""
        if config_path is None:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "data" / "sources.json"
        
        if not config_path.exists():
            logger.warning(f"Sources config file not found at {config_path}, using defaults")
            return self._get_default_sources()
        
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            
            sources = []
            for item in data:
                try:
                    source_type = SourceType(item['type'])
                    sources.append(MediaSource(
                        type=source_type,
                        name=item['name'],
                        uri=item['uri'],
                        source_type=item.get('source_type', 'music')
                    ))
                except (KeyError, ValueError) as e:
                    logger.error(f"Invalid source entry in config: {item}, error: {e}")
                    continue
            
            if not sources:
                logger.warning("No valid sources found in config file, using defaults")
                return self._get_default_sources()
            
            logger.info(f"Loaded {len(sources)} sources from {config_path}")
            return sources
            
        except Exception as e:
            logger.error(f"Error loading sources config file: {e}, using defaults")
            return self._get_default_sources()
    
    def _get_default_sources(self) -> List[MediaSource]:
        """Get default list of sources (fallback)"""
        return [
            MediaSource(
                type=SourceType.SPOTIFY_PLAYLIST,
                name="My Favorite Playlist",
                uri="spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
                source_type="music"
            ),
            MediaSource(
                type=SourceType.YOUTUBE_CHANNEL,
                name="Lofi Hip Hop",
                uri="https://www.youtube.com/@LofiGirl",
                source_type="music"
            ),
        ]
    
    def _save_current_index_to_db(self, index: int):
        """Save current source index to database using sync session"""
        from sqlalchemy import select
        
        try:
            with get_sync_session() as session:
                result = session.execute(
                    select(AppStateModel).where(AppStateModel.key == 'current_source_index')
                )
                app_state = result.scalar_one_or_none()
                
                if app_state:
                    app_state.value = str(index)
                else:
                    app_state = AppStateModel(key='current_source_index', value=str(index))
                    session.add(app_state)
                
                session.commit()
                logger.debug(f"Saved current_source_index {index} to database")
        except Exception as e:
            logger.warning(f"Failed to save current index to database: {e}")
    
    def get_current_source(self) -> Optional[MediaSource]:
        """Get current active source"""
        if not self.sources:
            return None
        return self.sources[self.current_source_index]
    
    def next_source(self) -> MediaSource:
        """Cycle to next source in list"""
        if not self.sources:
            raise ValueError("No sources available")
        
        self.current_source_index = (self.current_source_index + 1) % len(self.sources)
        source = self.sources[self.current_source_index]
        logger.info(f"Cycled to next source: {source.name} ({source.type.value})")
        
        # Save to database
        self._save_current_index_to_db(self.current_source_index)
        
        return source
    
    def previous_source(self) -> MediaSource:
        """Cycle to previous source in list"""
        if not self.sources:
            raise ValueError("No sources available")
        
        self.current_source_index = (self.current_source_index - 1) % len(self.sources)
        source = self.sources[self.current_source_index]
        logger.info(f"Cycled to previous source: {source.name} ({source.type.value})")
        
        # Save to database
        self._save_current_index_to_db(self.current_source_index)
        
        return source
    
    def add_source(self, source: MediaSource):
        """Add a new source to the list"""
        self.sources.append(source)
        logger.info(f"Added source: {source.name}")
    
    def remove_source(self, index: int):
        """Remove a source from the list"""
        if 0 <= index < len(self.sources):
            removed = self.sources.pop(index)
            if self.current_source_index >= len(self.sources):
                self.current_source_index = 0
            logger.info(f"Removed source: {removed.name}")
            self._save_current_index_to_db(self.current_source_index)
