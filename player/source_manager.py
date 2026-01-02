"""Source manager for YouTube channels and Spotify playlists"""

from typing import List, Optional
from dataclasses import dataclass
from enum import Enum
import logging
import json
from pathlib import Path

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


class SourceManager:
    """Manages list of sources and cycling through them"""
    
    def __init__(self, sources: Optional[List[MediaSource]] = None, config_path: Optional[Path] = None):
        """
        Initialize source manager
        
        Args:
            sources: List of media sources. If None, loads from config file or uses defaults
            config_path: Path to sources.json file. Defaults to data/sources.json relative to project root
        """
        if sources is not None:
            self.sources: List[MediaSource] = sources
        else:
            self.sources: List[MediaSource] = self._load_sources_from_file(config_path)
        
        self.current_source_index = 0
        logger.info(f"SourceManager initialized with {len(self.sources)} sources")
    
    def _load_sources_from_file(self, config_path: Optional[Path] = None) -> List[MediaSource]:
        """
        Load sources from JSON config file
        
        Args:
            config_path: Path to sources.json. If None, uses data/sources.json relative to project root
        
        Returns:
            List of MediaSource objects
        """
        if config_path is None:
            # Default to data/sources.json relative to project root
            # Assume we're in player/ directory, so go up one level
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
                        uri=item['uri']
                    ))
                except (KeyError, ValueError) as e:
                    logger.error(f"Invalid source entry in config: {item}, error: {e}")
                    continue
            
            if not sources:
                logger.warning("No valid sources found in config file, using defaults")
                return self._get_default_sources()
            
            logger.info(f"Loaded {len(sources)} sources from {config_path}")
            return sources
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in sources config file: {e}, using defaults")
            return self._get_default_sources()
        except Exception as e:
            logger.error(f"Error loading sources config file: {e}, using defaults")
            return self._get_default_sources()
    
    def _get_default_sources(self) -> List[MediaSource]:
        """Get default list of sources (fallback if config file not available)"""
        return [
            MediaSource(
                type=SourceType.SPOTIFY_PLAYLIST,
                name="My Favorite Playlist",
                uri="spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
            ),
            MediaSource(
                type=SourceType.YOUTUBE_CHANNEL,
                name="Lofi Hip Hop",
                uri="https://www.youtube.com/@LofiGirl"
            ),
        ]
    
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
        return source
    
    def previous_source(self) -> MediaSource:
        """Cycle to previous source in list"""
        if not self.sources:
            raise ValueError("No sources available")
        
        self.current_source_index = (self.current_source_index - 1) % len(self.sources)
        source = self.sources[self.current_source_index]
        logger.info(f"Cycled to previous source: {source.name} ({source.type.value})")
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

