"""Player service orchestrator for Mopidy and YouTube"""

import logging
import os
from typing import Optional, List
from datetime import datetime

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
        announcement_voice_model: Optional[str] = None,
        dev_mode: bool = False
    ):
        """
        Initialize player service
        
        Args:
            state: JukeboxState instance for coordination
            sources: Optional list of MediaSource objects. If None, uses defaults from SourceManager
            announcement_voice_model: Optional path to Piper voice model for announcements
            dev_mode: If True, skip auto-play when loading sources
        """
        self.state = state
        self.dev_mode = dev_mode
        self.source_manager = SourceManager(sources)
        self.youtube_client = YouTubeClient(state)
        
        # Initialize Mopidy thread (not started yet - will be started in lifespan)
        self.mopidy_thread = MopidyThread(state)
        
        # Get attenuation factor from environment or use default
        attenuation_factor = float(os.getenv('ANNOUNCEMENT_ATTENUATION_FACTOR', '0.3'))
        
        # Initialize announcement thread (not started yet - will be started in lifespan)
        # Pass self reference for volume attenuation support
        self.announcement_thread = AnnouncementThread(
            voice_model_path=announcement_voice_model,
            player_service=self,
            attenuation_factor=attenuation_factor
        )
        
        # Load initial source (will skip auto-play if dev_mode is True)
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
        
        # In dev mode, skip loading entirely to avoid interfering with running systemd services
        if self.dev_mode:
            # Just update state to reflect source type, but don't load anything
            if source.type == SourceType.SPOTIFY_PLAYLIST:
                with self.state.lock:
                    self.state.current_source = "playlist"
                logger.info(f"PlayerService: Dev mode - skipping playlist load for '{source.name}' (to avoid interfering with running Mopidy)")
            elif source.type == SourceType.YOUTUBE_CHANNEL:
                with self.state.lock:
                    self.state.current_source = "stream"
                logger.info(f"PlayerService: Dev mode - skipping channel load for '{source.name}' (to avoid interfering with running mpv)")
            else:
                logger.warning(f"PlayerService: Unknown source type: {source.type}")
            return
        
        # Normal mode: load the source
        if source.type == SourceType.SPOTIFY_PLAYLIST:
            # Update state to reflect source type
            with self.state.lock:
                self.state.current_source = "playlist"
            # Ensure volume is at 100% when loading Spotify playlist
            self.set_volume(100, sync=True)
            # Load playlist
            self._send_mopidy_command(
                CommandType.LOAD_PLAYLIST,
                {"playlist_uri": source.uri, "shuffle": True, "auto_play": True}
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
            if not self.state.is_playing:
                self._send_mopidy_command(CommandType.PLAY) # Ensure playback is resumed after next
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
            if not self.state.is_playing:
                self._send_mopidy_command(CommandType.PLAY) # Ensure playback is resumed after previous
            logger.info(f"PlayerService: Previous track for {current_source}")
        elif current_source == "stream":
            self.youtube_client.previous()
            logger.info(f"PlayerService: Previous video for {current_source}")
        else:
            logger.info(f"PlayerService: Previous track - source '{current_source}' not implemented")
    
    def cycle_source(self):
        """Cycle to next source in the list (non-blocking)"""
        # Get next source
        new_source = self.source_manager.next_source()

        # Announce the new source name
        self._announce_source(new_source.source_type, new_source.name)

        old_source = self.source_manager.get_current_source()
        
        # Stop current playback
        if old_source:
            if old_source.type == SourceType.SPOTIFY_PLAYLIST:
                self._send_mopidy_command(CommandType.STOP)
                logger.info(f"PlayerService: Stopped {old_source.name} playback")
            elif old_source.type == SourceType.YOUTUBE_CHANNEL:
                self.youtube_client.stop()
                logger.info(f"PlayerService: Stopped {old_source.name} playback")
        
        # Load and play new source
        self._load_current_source()
        
        
        logger.info(f"PlayerService: Cycled from '{old_source.name if old_source else 'None'}' to '{new_source.name}'")
    
    def get_current_volume(self) -> Optional[int]:
        """
        Get current volume level (only works for Mopidy source)
        
        Returns:
            Volume level (0-100) or -1 if disabled, or None if not Mopidy/not available
        """
        # Only get volume if Mopidy is the active source
        if self.state.current_source != "playlist":
            logger.debug("PlayerService: get_current_volume called but Mopidy is not active source")
            return None
        
        try:
            volume = self.mopidy_thread.get_volume()
            return volume
        except Exception as e:
            logger.error(f"PlayerService: get_current_volume error: {e}")
            return None
    
    def set_volume(self, volume: int, sync: bool = False):
        """
        Set volume level (only works for Mopidy source)
        
        Args:
            volume: Volume level (0-100)
            sync: If True, wait for volume to be set synchronously. If False, queue command asynchronously.
        """
        # Only set volume if Mopidy is the active source
        if self.state.current_source != "playlist":
            logger.debug("PlayerService: set_volume called but Mopidy is not active source")
            return
        
        # Clamp volume to valid range
        volume = max(0, min(100, volume))
        
        try:
            if sync:
                # Synchronous volume setting (for immediate effect)
                success = self.mopidy_thread.set_volume_sync(volume)
                if success:
                    logger.debug(f"PlayerService: Volume set to {volume} (synchronous)")
                else:
                    logger.warning(f"PlayerService: Failed to set volume synchronously")
            else:
                # Asynchronous volume setting (for non-critical changes)
                self._send_mopidy_command(CommandType.SET_VOLUME, {"volume": volume})
                logger.debug(f"PlayerService: Volume set to {volume} (asynchronous)")
        except Exception as e:
            logger.error(f"PlayerService: set_volume error: {e}")
    
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
    
    def announce_startup(self):
        """
        Announce startup message with current source using Tagalog greeting based on time of day
        """
        # Get current hour to determine time of day
        current_hour = datetime.now().hour
        
        # Determine greeting based on time:
        # Morning (umaga): 5:00 AM - 11:59 AM
        # Noon/Afternoon (tanghali): 12:00 PM - 5:59 PM
        # Evening/Night (gabi): 6:00 PM - 4:59 AM
        if 5 <= current_hour < 12:
            greeting = "Magandang umaga"
        elif 12 <= current_hour < 18:
            greeting = "Magandang tanghali"
        else:
            greeting = "Magandang gabi"
        
        source = self.source_manager.get_current_source()
        if source:
            announcement_text = f"{greeting}, now playing: {source.name}"
        else:
            announcement_text = f"{greeting}, system started"
        
        command = AnnouncementCommand(
            AnnouncementCommandType.ANNOUNCE,
            {"text": announcement_text}
        )
        self.announcement_thread.send_command(command)
        logger.debug(f"Startup announcement sent: {announcement_text}")