"""Mopidy thread with persistent MPD connection and command queue"""

import threading
import queue
import time
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from player.mopidy_client import MopidyClient
from gpio.state import JukeboxState

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Command types for Mopidy thread"""
    PLAY = "play"
    PAUSE = "pause"
    TOGGLE = "toggle"
    NEXT = "next"
    PREVIOUS = "previous"
    STOP = "stop"
    LOAD_PLAYLIST = "load_playlist"
    SHUTDOWN = "shutdown"


@dataclass
class Command:
    """Command to send to Mopidy thread"""
    type: CommandType
    data: Optional[dict] = None  # For commands that need parameters (e.g., load_playlist)


class MopidyThread(threading.Thread):
    """Thread for managing Mopidy operations with persistent MPD connection"""
    
    def __init__(self, state: JukeboxState, host: str = "localhost", port: int = 6600, poll_interval: float = 1.5):
        """
        Initialize Mopidy thread
        
        Args:
            state: JukeboxState instance for state synchronization
            host: MPD server host
            port: MPD server port
            poll_interval: State polling interval in seconds
        """
        super().__init__(name="MopidyThread", daemon=True)
        self.state = state
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        
        self.command_queue = queue.Queue()
        self.client: Optional[MopidyClient] = None
        self.running = False
        self.connected = False
        
        # Reconnection settings
        self.reconnect_delay = 5.0
        self.max_reconnect_delay = 60.0
        
        # Track last state poll time
        self.last_poll_time = 0.0
        
        logger.info(f"MopidyThread initialized (host={host}, port={port})")
    
    def run(self):
        """Main thread loop - handles connection, commands, and state polling"""
        self.running = True
        logger.info("MopidyThread started")
        
        while self.running:
            try:
                # Ensure connection
                if not self.connected:
                    self._connect()
                    if not self.connected:
                        # Connection failed, wait before retry
                        time.sleep(self.reconnect_delay)
                        self.reconnect_delay = min(self.reconnect_delay * 1.5, self.max_reconnect_delay)
                        continue
                    else:
                        # Reset reconnect delay on successful connection
                        self.reconnect_delay = 5.0
                
                # Process commands (non-blocking with timeout)
                try:
                    command = self.command_queue.get(timeout=0.1)
                    self._process_command(command)
                except queue.Empty:
                    pass
                
                # Poll state at configured interval
                current_time = time.time()
                if current_time - self.last_poll_time >= self.poll_interval:
                    self._poll_state()
                    self.last_poll_time = current_time
                
                # Sleep before next iteration
                time.sleep(0.1)  # Small sleep to prevent tight loop
                
            except Exception as e:
                logger.error(f"MopidyThread error: {e}", exc_info=True)
                self.connected = False
                if self.client:
                    try:
                        self.client.disconnect()
                    except:
                        pass
                    self.client = None
                time.sleep(self.reconnect_delay)
        
        # Cleanup
        self._disconnect()
        logger.info("MopidyThread stopped")
    
    def _connect(self):
        """Establish connection to MPD server"""
        try:
            if self.client is None:
                self.client = MopidyClient()
            
            if not self.client.is_connected():
                self.client.connect(self.host, self.port)
            
            if self.client.is_connected():
                self.connected = True
                logger.info(f"Connected to Mopidy MPD server at {self.host}:{self.port}")
            else:
                self.connected = False
        except Exception as e:
            logger.warning(f"Failed to connect to Mopidy: {e}")
            self.connected = False
            if self.client:
                try:
                    self.client.disconnect()
                except:
                    pass
    
    def _disconnect(self):
        """Disconnect from MPD server"""
        if self.client:
            try:
                self.client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting from Mopidy: {e}")
            self.client = None
        self.connected = False
    
    def _process_command(self, command: Command):
        """Process a command from the queue"""
        if not self.connected or not self.client:
            logger.warning(f"Cannot process command {command.type.value}: not connected")
            return
        
        try:
            if command.type == CommandType.PLAY:
                self.client.play()
            elif command.type == CommandType.PAUSE:
                self.client.pause()
            elif command.type == CommandType.TOGGLE:
                # Query actual Mopidy state and toggle accordingly
                playback_state = self.client.get_playback_state()
                if playback_state == "play":
                    self.client.pause()
                    logger.debug("MopidyThread: Toggled from play to pause")
                elif playback_state == "pause":
                    self.client.play()
                    logger.debug("MopidyThread: Toggled from pause to play")
                else:
                    # If stopped, start playing
                    self.client.play()
                    logger.debug("MopidyThread: Toggled from stop to play")
            elif command.type == CommandType.NEXT:
                self.client.next()
            elif command.type == CommandType.PREVIOUS:
                self.client.previous()
            elif command.type == CommandType.STOP:
                self.client.stop()
            elif command.type == CommandType.LOAD_PLAYLIST:
                playlist_uri = command.data.get("playlist_uri") if command.data else None
                shuffle = command.data.get("shuffle", True) if command.data else True
                if playlist_uri:
                    self.client.load_playlist(playlist_uri, shuffle)
                else:
                    logger.warning("LoadPlaylistCommand missing playlist_uri")
            elif command.type == CommandType.SHUTDOWN:
                self.running = False
            else:
                logger.warning(f"Unknown command type: {command.type}")
        except Exception as e:
            logger.error(f"Error processing command {command.type.value}: {e}")
            # Mark as disconnected to trigger reconnection
            self.connected = False
    
    def _poll_state(self):
        """Poll Mopidy state and update JukeboxState"""
        if not self.connected or not self.client:
            return
        
        try:
            # Get playback state
            playback_state = self.client.get_playback_state()
            current_track = self.client.get_current_track()
            
            # Update JukeboxState (thread-safe via lock)
            with self.state.lock:
                # Update playing state
                if playback_state == "play":
                    self.state.is_playing = True
                elif playback_state in ["pause", "stop"]:
                    self.state.is_playing = False
                
                # Update current track
                if current_track:
                    self.state.current_track = current_track
                elif playback_state == "stop":
                    self.state.current_track = None
                    
        except Exception as e:
            logger.debug(f"Error polling Mopidy state: {e}")
            # Don't mark as disconnected for polling errors, just log
    
    def send_command(self, command: Command):
        """Send a command to the thread (non-blocking)"""
        try:
            self.command_queue.put_nowait(command)
        except queue.Full:
            logger.warning("Command queue full, dropping command")
    
    def stop_thread(self):
        """Stop the thread gracefully"""
        self.running = False
        self.send_command(Command(CommandType.SHUTDOWN))
        self.join(timeout=5.0)
        if self.is_alive():
            logger.warning("MopidyThread did not stop gracefully")

