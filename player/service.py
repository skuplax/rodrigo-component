"""Player service orchestrator for Mopidy and YouTube"""

import logging
from typing import Optional, List

from player.mopidy_thread import MopidyThread, Command, CommandType
from player.youtube_client import YouTubeClient
from player.source_manager import SourceManager, MediaSource, SourceType
from player.announcement_thread import AnnouncementThread, AnnouncementCommand, AnnouncementCommandType
from gpio.state import JukeboxState

logger = logging.getLogger(__name__)


class PlayerService:
    """Orchestrates Mopidy (Spotify) and YouTube playback"""
    
    def __init__(
        self,
        state: JukeboxState,
        sources: Optional[List[MediaSource]] = None,
        announcement_voice_model: Optional[str] = None
    ):
        """
        Initialize player service
        
        Args:
            state: JukeboxState instance for coordination
            sources: Optional list of MediaSource objects. If None, uses defaults from SourceManager
            announcement_voice_model: Optional path to Piper voice model for announcements
        """
        self.state = state
        self.source_manager = SourceManager(sources)
        self.youtube_client = YouTubeClient(state)
        
        # Initialize Mopidy thread (not started yet - will be started in lifespan)
        self.mopidy_thread = MopidyThread(state)
        
        # Initialize announcement thread (not started yet - will be started in lifespan)
        self.announcement_thread = AnnouncementThread(voice_model_path=announcement_voice_model)
        
        # Load initial source
        self._load_current_source()
        
        logger.info("PlayerService initialized")
    
    def start(self):
        """Start the Mopidy, YouTube, and Announcement threads"""
        if not self.mopidy_thread.is_alive():
            self.mopidy_thread.start()
            logger.info("MopidyThread started")
        
        # Start YouTube thread
        self.youtube_client.start()
        
        # Start announcement thread
        if not self.announcement_thread.is_alive():
            self.announcement_thread.start()
            logger.info("AnnouncementThread started")
    
    def stop(self):
        """Stop the Mopidy, YouTube, and Announcement threads gracefully"""
        if self.mopidy_thread.is_alive():
            self.mopidy_thread.stop_thread()
            logger.info("MopidyThread stopped")
        
        # Stop YouTube thread
        self.youtube_client.stop_thread()
        
        # Stop announcement thread
        if self.announcement_thread.is_alive():
            self.announcement_thread.stop_thread()
            logger.info("AnnouncementThread stopped")
    
    def _send_mopidy_command(self, command_type: CommandType, data: Optional[dict] = None):
        """Send a command to Mopidy thread (non-blocking)"""
        command = Command(command_type, data)
        self.mopidy_thread.send_command(command)
    
    def _load_current_source(self):
        """Load the current source from source manager"""
        source = self.source_manager.get_current_source()
        if not source:
            logger.warning("No current source available")
            return
        
        if source.type == SourceType.SPOTIFY_PLAYLIST:
            # Update state to reflect source type
            with self.state.lock:
                self.state.current_source = "playlist"
            # Load playlist
            self._send_mopidy_command(
                CommandType.LOAD_PLAYLIST,
                {"playlist_uri": source.uri, "shuffle": True}
            )
            logger.info(f"PlayerService: Loaded playlist '{source.name}'")
        elif source.type == SourceType.YOUTUBE_CHANNEL:
            # Update state to reflect source type
            with self.state.lock:
                self.state.current_source = "stream"
            # Load channel
            self.youtube_client.play_channel(source.uri)
            logger.info(f"PlayerService: Loaded channel '{source.name}'")
        else:
            logger.warning(f"PlayerService: Unknown source type: {source.type}")
    
    def toggle_play(self):
        """Send play/pause signal based on current source (non-blocking)"""
        current_source = self.state.current_source
        
        if current_source == "playlist":
            # Toggle Mopidy playback - use TOGGLE command which queries actual state
            self._send_mopidy_command(CommandType.TOGGLE)
            logger.info(f"PlayerService: Toggle play/pause for {current_source}")
        elif current_source == "stream":
            # Toggle YouTube playback
            if self.state.is_playing:
                self.youtube_client.pause()
            else:
                self.youtube_client.resume()
            logger.info(f"PlayerService: Toggle play/pause for {current_source}")
        else:
            logger.info(f"PlayerService: Toggle play/pause - source '{current_source}' not implemented")
    
    def next(self):
        """Send next track signal (non-blocking) - loops within current source"""
        current_source = self.state.current_source
        
        if current_source == "playlist":
            # Mopidy handles looping automatically when at end of playlist
            self._send_mopidy_command(CommandType.NEXT)
            logger.info(f"PlayerService: Next track for {current_source}")
        elif current_source == "stream":
            # YouTube client handles looping (resets when all watched)
            self.youtube_client.next()
            logger.info(f"PlayerService: Next video for {current_source}")
        else:
            logger.info(f"PlayerService: Next track - source '{current_source}' not implemented")
    
    def previous(self):
        """Send previous track signal (non-blocking)"""
        current_source = self.state.current_source
        
        if current_source == "playlist":
            self._send_mopidy_command(CommandType.PREVIOUS)
            logger.info(f"PlayerService: Previous track for {current_source}")
        elif current_source == "stream":
            self.youtube_client.previous()
            logger.info(f"PlayerService: Previous video for {current_source}")
        else:
            logger.info(f"PlayerService: Previous track - source '{current_source}' not implemented")
    
    def cycle_source(self):
        """Cycle to next source in the list (non-blocking)"""
        old_source = self.source_manager.get_current_source()
        
        # Stop current playback
        if old_source:
            if old_source.type == SourceType.SPOTIFY_PLAYLIST:
                self._send_mopidy_command(CommandType.STOP)
                logger.info(f"PlayerService: Stopped {old_source.name} playback")
            elif old_source.type == SourceType.YOUTUBE_CHANNEL:
                self.youtube_client.stop()
                logger.info(f"PlayerService: Stopped {old_source.name} playback")
        
        # Get next source
        new_source = self.source_manager.next_source()
        
        # Load and play new source
        self._load_current_source()
        
        # Announce the new source name
        self._announce_source(new_source.source_type, new_source.name)
        
        logger.info(f"PlayerService: Cycled from '{old_source.name if old_source else 'None'}' to '{new_source.name}'")
    
    def _announce_source(self, source_type: str, source_name: str):
        """
        Announce source name via announcement service
        
        Args:
            source_type: Category of source ("music" or "news")
            source_name: Name of the source to announce
        """
        announcement_text = f"{source_type}, {source_name}"
        command = AnnouncementCommand(
            AnnouncementCommandType.ANNOUNCE,
            {"text": announcement_text}
        )
        self.announcement_thread.send_command(command)
        logger.debug(f"Announcement sent: {announcement_text}")
