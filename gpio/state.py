"""Thread-safe state management for jukebox and GPIO events"""

from threading import Lock
from collections import deque
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class JukeboxState:
    """Thread-safe state manager for jukebox and GPIO events"""
    
    def __init__(self):
        self.lock = Lock()
        self.current_track = None
        self.is_playing = False
        self.current_source = "radio"  # Default source
        self.sources = ["radio", "playlist", "stream"]  # Available sources
        self.button_events = deque(maxlen=100)  # Last 100 events
        self.gpio_status = {
            17: {"name": "Play/Pause", "state": "released"},
            27: {"name": "Previous", "state": "released"},
            22: {"name": "Next", "state": "released"},
            23: {"name": "Cycle Source", "state": "released"},
        }
        
    def add_event(self, pin: int, event_type: str, action: str):
        """Add a GPIO event to the history"""
        with self.lock:
            event = {
                "pin": pin,
                "event": event_type,
                "action": action,
                "timestamp": datetime.now().isoformat()
            }
            self.button_events.append(event)
            # Update GPIO status
            if pin in self.gpio_status:
                self.gpio_status[pin]["state"] = event_type
            logger.info(f"GPIO Event: Pin {pin} ({self.gpio_status.get(pin, {}).get('name', 'Unknown')}) - {event_type}")
    
    def get_recent_events(self, limit: int = 10):
        """Get recent GPIO events"""
        with self.lock:
            return list(self.button_events)[-limit:]
    
    def toggle_play(self):
        """Toggle play/pause state"""
        with self.lock:
            self.is_playing = not self.is_playing
            logger.info(f"Play/Pause toggled: {'Playing' if self.is_playing else 'Paused'}")
            return self.is_playing
    
    def cycle_source(self):
        """Cycle through available sources"""
        with self.lock:
            current_idx = self.sources.index(self.current_source)
            next_idx = (current_idx + 1) % len(self.sources)
            self.current_source = self.sources[next_idx]
            logger.info(f"Source cycled to: {self.current_source}")
            return self.current_source
    
    def get_state(self):
        """Get current jukebox state"""
        with self.lock:
            return {
                "is_playing": self.is_playing,
                "current_track": self.current_track,
                "current_source": self.current_source,
                "available_sources": self.sources,
                "gpio_status": self.gpio_status.copy()
            }

