"""Mopidy MPD client wrapper"""

import logging
from typing import Optional, Tuple
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
    
    def load_playlist(self, playlist_uri: str, shuffle: bool = True, auto_play: bool = True):
        """
        Load a Spotify playlist with optional shuffle
        
        Args:
            playlist_uri: Spotify playlist URI (e.g., spotify:playlist:xxx)
            shuffle: Whether to shuffle the playlist
            auto_play: Whether to start playing immediately after loading
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
            
            # Start playing only if auto_play is True
            if auto_play:
                self.client.play()
                logger.info(f"MopidyClient: Loaded playlist '{playlist_uri}' with shuffle={shuffle}, auto_play=True")
            else:
                logger.info(f"MopidyClient: Loaded playlist '{playlist_uri}' with shuffle={shuffle}, auto_play=False")
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
    
    def get_volume(self) -> Optional[int]:
        """
        Get current volume level
        
        Returns:
            Volume level (0-100) or -1 if disabled, or None if not connected/error
        """
        if not self.is_connected():
            return None
        try:
            status = self.client.status()
            volume_str = status.get("volume", "-1")
            volume = int(volume_str)
            logger.debug(f"MopidyClient: Current volume: {volume}")
            return volume
        except (ValueError, KeyError) as e:
            logger.debug(f"MopidyClient: Get volume failed: {e}")
            return None
        except Exception as e:
            logger.error(f"MopidyClient: Get volume error: {e}")
            return None
    
    def set_volume(self, volume: int):
        """
        Set volume level
        
        Args:
            volume: Volume level (0-100). Values outside range will be clamped.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Mopidy")
        
        # Clamp volume to valid range
        volume = max(0, min(100, volume))
        
        try:
            self.client.setvol(volume)
            logger.debug(f"MopidyClient: Volume set to {volume}")
        except Exception as e:
            logger.error(f"MopidyClient: Set volume failed: {e}")
            raise
    
    def get_time(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Get current playhead position and total duration in seconds
        
        Returns:
            Tuple of (position, duration) in seconds, or (None, None) if not connected/error/no track
            MPD returns time as "current:total" (e.g., "123:456")
        """
        if not self.is_connected():
            return (None, None)
        try:
            status = self.client.status()
            time_str = status.get("time")
            if time_str:
                # MPD returns time as "current:total" (e.g., "123:456")
                parts = time_str.split(":")
                if len(parts) == 2:
                    return (float(parts[0]), float(parts[1]))
            return (None, None)
        except Exception as e:
            logger.debug(f"MopidyClient: Get time failed: {e}")
            return (None, None)