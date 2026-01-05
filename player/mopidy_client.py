"""Mopidy MPD client wrapper"""

import logging
from typing import Optional
import mpd

logger = logging.getLogger(__name__)


class MopidyClient:
    """Client for controlling Mopidy via MPD protocol"""
    
    def __init__(self):
        """Initialize MPD client (connection happens separately)"""
        self.client = mpd.MPDClient()
        self._connected = False
        logger.debug("MopidyClient initialized")
    
    def connect(self, host: str = "localhost", port: int = 6600):
        """
        Connect to Mopidy MPD server
        
        Args:
            host: MPD server host
            port: MPD server port
        """
        try:
            if self._connected:
                try:
                    self.client.ping()
                    return  # Already connected
                except:
                    # Connection lost, disconnect first
                    try:
                        self.client.disconnect()
                    except:
                        pass
                    self._connected = False
            
            self.client.connect(host, port)
            self._connected = True
            logger.info(f"Connected to Mopidy MPD server at {host}:{port}")
        except Exception as e:
            logger.warning(f"Failed to connect to Mopidy: {e}")
            self._connected = False
            raise
    
    def disconnect(self):
        """Disconnect from MPD server"""
        try:
            if self._connected:
                self.client.disconnect()
                self._connected = False
                logger.debug("Disconnected from Mopidy MPD server")
        except Exception as e:
            logger.warning(f"Error disconnecting from Mopidy: {e}")
            self._connected = False
    
    def is_connected(self) -> bool:
        """Check if connected to MPD server"""
        if not self._connected:
            return False
        try:
            self.client.ping()
            return True
        except:
            self._connected = False
            return False
    
    def play(self):
        """Send play command to Mopidy"""
        if not self.is_connected():
            raise ConnectionError("Not connected to Mopidy")
        try:
            self.client.play()
            logger.debug("MopidyClient: Play command sent")
        except Exception as e:
            logger.error(f"MopidyClient: Play command failed: {e}")
            raise
    
    def pause(self):
        """Send pause command to Mopidy"""
        if not self.is_connected():
            raise ConnectionError("Not connected to Mopidy")
        try:
            self.client.pause()
            logger.debug("MopidyClient: Pause command sent")
        except Exception as e:
            logger.error(f"MopidyClient: Pause command failed: {e}")
            raise
    
    def next(self):
        """Send next track command to Mopidy"""
        if not self.is_connected():
            raise ConnectionError("Not connected to Mopidy")
        try:
            self.client.next()
            logger.debug("MopidyClient: Next track command sent")
        except Exception as e:
            logger.error(f"MopidyClient: Next track command failed: {e}")
            raise
    
    def previous(self):
        """Send previous track command to Mopidy"""
        if not self.is_connected():
            raise ConnectionError("Not connected to Mopidy")
        try:
            self.client.previous()
            logger.debug("MopidyClient: Previous track command sent")
        except Exception as e:
            logger.error(f"MopidyClient: Previous track command failed: {e}")
            raise
    
    def stop(self):
        """Stop playback"""
        if not self.is_connected():
            raise ConnectionError("Not connected to Mopidy")
        try:
            self.client.stop()
            logger.debug("MopidyClient: Stop command sent")
        except Exception as e:
            logger.error(f"MopidyClient: Stop command failed: {e}")
            raise
    
    def load_playlist(self, playlist_uri: str, shuffle: bool = True):
        """
        Load a Spotify playlist with optional shuffle
        
        Args:
            playlist_uri: Spotify playlist URI (e.g., spotify:playlist:xxx)
            shuffle: Whether to shuffle the playlist
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Mopidy")
        try:
            # Clear current playlist
            self.client.clear()
            
            # Add playlist tracks to queue (MPD 'add' command works with Spotify URIs)
            self.client.add(playlist_uri)
            
            # Shuffle if requested
            if shuffle:
                self.client.random(1)
            
            # Start playing
            self.client.play()
            logger.info(f"MopidyClient: Loaded playlist '{playlist_uri}' with shuffle={shuffle}")
        except Exception as e:
            logger.error(f"MopidyClient: Load playlist failed: {e}")
            raise
    
    def get_playback_state(self) -> str:
        """
        Get current playback state
        
        Returns:
            "play", "pause", or "stop"
        """
        if not self.is_connected():
            return "stop"
        try:
            status = self.client.status()
            return status.get("state", "stop")
        except Exception as e:
            logger.debug(f"MopidyClient: Get playback state failed: {e}")
            return "stop"
    
    def get_current_track(self) -> Optional[dict]:
        """
        Get current track information
        
        Returns:
            Dictionary with track info (title, artist, album, etc.) or None
        """
        if not self.is_connected():
            return None
        try:
            current_song = self.client.currentsong()
            if current_song:
                return {
                    "title": current_song.get("title", "Unknown"),
                    "artist": current_song.get("artist", "Unknown Artist"),
                    "album": current_song.get("album", ""),
                    "uri": current_song.get("file", ""),
                }
            return None
        except Exception as e:
            logger.debug(f"MopidyClient: Get current track failed: {e}")
            return None
