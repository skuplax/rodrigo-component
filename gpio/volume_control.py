"""Rotary encoder volume control with proper quadrature decoding

Uses the shared VolumeService to ensure max volume limit is respected
and volume scale matches alsamixer (mapped volume).
"""

from gpiozero import RotaryEncoder, Button
import logging
import time
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)


class VolumeControl:
    """Rotary encoder volume control with throttling and proper state management.
    
    Uses VolumeService for volume operations to ensure:
    - Max volume limit is respected
    - Mapped volume scale matches alsamixer
    - Consistent behavior between GPIO and web controls
    """
    
    def __init__(
        self, 
        player_service=None,  # Optional, not used for ALSA control
        clk_pin: int = 5,   # KY-040 default: GPIO 5
        dt_pin: int = 6,    # KY-040 default: GPIO 6
        sw_pin: Optional[int] = 13,  # KY-040 default: GPIO 13
        update_throttle_ms: int = 50,
        alsa_control: str = "PCM",  # ALSA control name (PCM or Master)
        volume_per_step: int = 2  # Volume change per encoder step (1-10 recommended)
    ):
        """
        Initialize rotary encoder for ALSA PCM volume control
        
        Args:
            player_service: Optional PlayerService instance (not used for ALSA control)
            clk_pin: GPIO pin for CLK (clock) signal
            dt_pin: GPIO pin for DT (data) signal  
            sw_pin: Optional GPIO pin for switch/button (mute/unmute)
            update_throttle_ms: Minimum time between volume updates in milliseconds
            alsa_control: ALSA control name (default: "PCM")
            volume_per_step: Volume change per encoder step/click (default: 2%)
        """
        self.player_service = player_service
        self.alsa_control = alsa_control
        self.volume_per_step = max(1, min(10, volume_per_step))  # Clamp to 1-10
        self.current_volume = 50  # Track current volume
        self.volume_lock = Lock()
        self.last_volume_update = 0
        self.update_throttle_ms = update_throttle_ms
        self.encoder = None
        self.button = None
        self.volume_service = None
        
        # Initialize VolumeService for volume operations
        try:
            from audio.volume import get_volume_service
            self.volume_service = get_volume_service()
            logger.info("GPIO VolumeControl using shared VolumeService")
        except Exception as e:
            logger.warning(f"Could not initialize VolumeService: {e}")
            logger.warning("GPIO volume control will operate without max limit enforcement")
        
        try:
            # gpiozero RotaryEncoder handles quadrature decoding automatically
            # Use larger max_steps since we're tracking volume separately
            self.encoder = RotaryEncoder(
                clk_pin, 
                dt_pin, 
                max_steps=200,  # Larger range for finer control
                wrap=False,     # Don't wrap around
                bounce_time=0.001  # Very short bounce time for fast rotation
            )
            
            # Use direction-specific callbacks for per-step volume changes
            self.encoder.when_rotated_clockwise = self._on_rotate_clockwise
            self.encoder.when_rotated_counter_clockwise = self._on_rotate_counter_clockwise
            
            # Optional: handle button press (mute/unmute)
            if sw_pin:
                self.button = Button(sw_pin, pull_up=True, bounce_time=0.01)
                self.button.when_pressed = self._on_button_press
                logger.info(f"Volume encoder button initialized on GPIO {sw_pin}")
                
            logger.info(f"Rotary encoder initialized on CLK={clk_pin}, DT={dt_pin} (step: {self.volume_per_step}%)")
            
            # Sync with current volume on startup
            self.sync_volume()
            
        except Exception as e:
            logger.error(f"Error initializing rotary encoder: {e}")
            logger.warning("Volume control will be disabled")
            self.encoder = None
    
    def _on_rotate_clockwise(self):
        """Handle clockwise rotation - increase volume"""
        self._adjust_volume(self.volume_per_step)
    
    def _on_rotate_counter_clockwise(self):
        """Handle counter-clockwise rotation - decrease volume"""
        self._adjust_volume(-self.volume_per_step)
    
    def _adjust_volume(self, delta: int):
        """Adjust volume by delta amount with throttling.
        
        Uses VolumeService which:
        - Respects the max volume limit
        - Uses mapped volume scale (matches alsamixer)
        """
        # Throttle updates to prevent overwhelming the system
        current_time = time.time() * 1000  # milliseconds
        if current_time - self.last_volume_update < self.update_throttle_ms:
            return
        
        with self.volume_lock:
            self.last_volume_update = current_time
            
            if self.volume_service:
                # Use VolumeService for volume operations (respects max limit)
                if delta > 0:
                    new_volume = self.volume_service.volume_up(abs(delta))
                else:
                    new_volume = self.volume_service.volume_down(abs(delta))
                
                self.current_volume = new_volume
                logger.debug(f"Volume changed to {new_volume}% (delta: {delta:+d}, max_limit: {self.volume_service.max_limit}%)")
            else:
                # Fallback: direct ALSA control without limit enforcement
                new_volume = max(0, min(100, self.current_volume + delta))
                if new_volume != self.current_volume:
                    self.current_volume = new_volume
                    self._set_alsa_volume_direct(new_volume)
                    logger.debug(f"ALSA {self.alsa_control} volume changed to {new_volume}% (delta: {delta:+d})")
    
    def _on_button_press(self):
        """Handle button press (mute/unmute)"""
        if self.volume_service:
            # Use VolumeService for mute toggle
            self.volume_service.toggle_mute()
            # Sync our tracked volume
            new_volume = self.volume_service.get_volume()
            if new_volume is not None:
                with self.volume_lock:
                    self.current_volume = new_volume
            logger.info(f"Volume mute toggled via VolumeService")
        else:
            # Fallback: direct ALSA mute control
            current = self._get_alsa_volume_direct()
            if current is None:
                current = self.current_volume
                
            if current > 0:
                # Mute: save current volume and set to 0
                self._saved_volume = current
                self._set_alsa_volume_direct(0)
                self._set_alsa_mute_direct(True)
                logger.info(f"ALSA {self.alsa_control} muted (was {current}%)")
            else:
                # Unmute: restore saved volume
                restored = getattr(self, '_saved_volume', 50)
                if restored <= 0:
                    restored = 50
                self._set_alsa_mute_direct(False)
                self._set_alsa_volume_direct(restored)
                with self.volume_lock:
                    self.current_volume = restored
                logger.info(f"ALSA {self.alsa_control} unmuted to {restored}%")
    
    def _get_alsa_volume_direct(self) -> Optional[int]:
        """Get current ALSA volume percentage (direct, fallback only)"""
        import subprocess
        import re
        try:
            result = subprocess.run(
                ['amixer', '-M', 'get', self.alsa_control],
                capture_output=True,
                text=True,
                check=True,
                timeout=1.0
            )
            # Parse output to extract volume percentage
            match = re.search(r'\[(\d+)%\]', result.stdout)
            if match:
                return int(match.group(1))
            return None
        except Exception as e:
            logger.debug(f"Error getting ALSA volume: {e}")
            return None
    
    def _set_alsa_volume_direct(self, volume_percent: int):
        """Set ALSA volume percentage (direct, fallback only)"""
        import subprocess
        try:
            subprocess.run(
                ['amixer', '-M', 'set', self.alsa_control, f'{volume_percent}%'],
                check=True,
                timeout=1.0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logger.warning(f"Error setting ALSA volume: {e}")
    
    def _set_alsa_mute_direct(self, mute: bool):
        """Set ALSA mute state (direct, fallback only)"""
        import subprocess
        try:
            state = 'mute' if mute else 'unmute'
            subprocess.run(
                ['amixer', '-M', 'set', self.alsa_control, state],
                check=True,
                timeout=1.0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logger.warning(f"Error setting ALSA mute: {e}")
    
    def sync_volume(self):
        """Sync tracked volume with current ALSA volume"""
        if not self.encoder:
            return
        
        if self.volume_service:
            # Get volume from VolumeService
            current = self.volume_service.get_volume()
        else:
            # Fallback to direct ALSA query
            current = self._get_alsa_volume_direct()
        
        if current is not None and current >= 0:
            with self.volume_lock:
                self.current_volume = current
                logger.debug(f"Volume encoder synced to {current}%")
    
    def close(self):
        """Cleanup resources"""
        if self.encoder:
            try:
                self.encoder.close()
                logger.info("Volume encoder closed")
            except Exception as e:
                logger.error(f"Error closing encoder: {e}")
        
        if self.button:
            try:
                self.button.close()
                logger.info("Volume encoder button closed")
            except Exception as e:
                logger.error(f"Error closing encoder button: {e}")
