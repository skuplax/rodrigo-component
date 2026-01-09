"""ALSA Volume Control Service

Provides volume control and max volume limiting for the system.
Uses mapped volume (-M flag) to match alsamixer's display.
"""

import subprocess
import re
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Database key for persisting max volume limit
MAX_VOLUME_LIMIT_KEY = "max_volume_limit"


@dataclass
class VolumeState:
    """Current volume state"""
    current: int  # 0-100 percentage (mapped scale, matches alsamixer)
    max_limit: int  # 0-100 percentage (user-defined max)
    muted: bool
    control_name: str


class VolumeService:
    """Service for controlling ALSA volume with max limit support.
    
    Uses mapped volume scale (-M flag) to match alsamixer's display.
    This provides perceptually linear volume control.
    """
    
    def __init__(self, control_name: str = "PCM", max_limit: int = 100):
        """
        Initialize volume service.
        
        Args:
            control_name: ALSA mixer control name (default: PCM for Raspberry Pi)
            max_limit: Maximum allowed volume percentage (0-100)
        """
        self.control_name = control_name
        self._available = self._check_availability()
        
        # Load max_limit from database, fallback to provided value
        self._max_limit = self._load_max_limit_from_db() or max(0, min(100, max_limit))
        
        if not self._available:
            logger.warning(f"ALSA control '{control_name}' not available")
        else:
            logger.info(f"VolumeService initialized with max_limit={self._max_limit}%")
    
    def _load_max_limit_from_db(self) -> Optional[int]:
        """Load max volume limit from database"""
        try:
            from db.database import get_sync_session
            from db.models import AppState
            
            with get_sync_session() as session:
                state = session.query(AppState).filter_by(key=MAX_VOLUME_LIMIT_KEY).first()
                if state and state.value:
                    return max(0, min(100, int(state.value)))
        except Exception as e:
            logger.warning(f"Failed to load max volume limit from DB: {e}")
        return None
    
    def _save_max_limit_to_db(self, value: int):
        """Save max volume limit to database"""
        try:
            from db.database import get_sync_session
            from db.models import AppState
            
            with get_sync_session() as session:
                state = session.query(AppState).filter_by(key=MAX_VOLUME_LIMIT_KEY).first()
                if state:
                    state.value = str(value)
                else:
                    session.add(AppState(key=MAX_VOLUME_LIMIT_KEY, value=str(value)))
                session.commit()
            logger.debug(f"Saved max volume limit to DB: {value}%")
        except Exception as e:
            logger.error(f"Failed to save max volume limit to DB: {e}")
    
    def _check_availability(self) -> bool:
        """Check if ALSA control is available"""
        try:
            result = subprocess.run(
                ["amixer", "-M", "sget", self.control_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking ALSA availability: {e}")
            return False
    
    @property
    def available(self) -> bool:
        """Check if volume control is available"""
        return self._available
    
    @property
    def max_limit(self) -> int:
        """Get current max volume limit"""
        return self._max_limit
    
    @max_limit.setter
    def max_limit(self, value: int):
        """Set max volume limit and enforce it"""
        self._max_limit = max(0, min(100, value))
        
        # Persist to database
        self._save_max_limit_to_db(self._max_limit)
        
        # Enforce limit on current volume if needed
        current = self.get_volume()
        if current is not None and current > self._max_limit:
            self.set_volume(self._max_limit)
            logger.info(f"Volume reduced to max limit: {self._max_limit}%")
    
    def get_volume(self) -> Optional[int]:
        """
        Get current volume percentage using mapped scale (matches alsamixer).
        
        Returns:
            Volume percentage (0-100) or None if unavailable
        """
        if not self._available:
            return None
        
        try:
            # Use -M for mapped volume to match alsamixer
            result = subprocess.run(
                ["amixer", "-M", "sget", self.control_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            # Parse percentage from output like "[66%]"
            match = re.search(r'\[(\d+)%\]', result.stdout)
            if match:
                return int(match.group(1))
            
            return None
        except Exception as e:
            logger.error(f"Error getting volume: {e}")
            return None
    
    def is_muted(self) -> bool:
        """Check if audio is muted"""
        if not self._available:
            return False
        
        try:
            result = subprocess.run(
                ["amixer", "-M", "sget", self.control_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False
            
            # Check for [off] in output
            return "[off]" in result.stdout
        except Exception as e:
            logger.error(f"Error checking mute status: {e}")
            return False
    
    def set_volume(self, percentage: int) -> bool:
        """
        Set volume percentage using mapped scale (matches alsamixer).
        
        Args:
            percentage: Target volume (0-100)
            
        Returns:
            True if successful
        """
        if not self._available:
            return False
        
        # Clamp to valid range and max limit
        percentage = max(0, min(percentage, self._max_limit))
        
        try:
            # Use -M for mapped volume to match alsamixer
            result = subprocess.run(
                ["amixer", "-M", "sset", self.control_name, f"{percentage}%"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.debug(f"Volume set to {percentage}%")
                return True
            else:
                logger.error(f"Failed to set volume: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error setting volume: {e}")
            return False
    
    def set_mute(self, muted: bool) -> bool:
        """
        Set mute state.
        
        Args:
            muted: True to mute, False to unmute
            
        Returns:
            True if successful
        """
        if not self._available:
            return False
        
        try:
            state = "mute" if muted else "unmute"
            result = subprocess.run(
                ["amixer", "sset", self.control_name, state],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.debug(f"Mute set to {muted}")
                return True
            else:
                logger.error(f"Failed to set mute: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error setting mute: {e}")
            return False
    
    def toggle_mute(self) -> bool:
        """Toggle mute state"""
        return self.set_mute(not self.is_muted())
    
    def volume_up(self, step: int = 5) -> int:
        """
        Increase volume by step percentage.
        
        Args:
            step: Percentage to increase
            
        Returns:
            New volume percentage
        """
        current = self.get_volume()
        if current is None:
            return 0
        
        new_volume = min(current + step, self._max_limit)
        self.set_volume(new_volume)
        return new_volume
    
    def volume_down(self, step: int = 5) -> int:
        """
        Decrease volume by step percentage.
        
        Args:
            step: Percentage to decrease
            
        Returns:
            New volume percentage
        """
        current = self.get_volume()
        if current is None:
            return 0
        
        new_volume = max(current - step, 0)
        self.set_volume(new_volume)
        return new_volume
    
    def get_state(self) -> VolumeState:
        """Get complete volume state"""
        return VolumeState(
            current=self.get_volume() or 0,
            max_limit=self._max_limit,
            muted=self.is_muted(),
            control_name=self.control_name
        )


# Singleton instance
_volume_service: Optional[VolumeService] = None


def get_volume_service() -> VolumeService:
    """Get or create the volume service singleton"""
    global _volume_service
    if _volume_service is None:
        _volume_service = VolumeService()
    return _volume_service

