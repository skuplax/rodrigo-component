"""GPIO button monitor with event callbacks"""

from gpiozero import Button
import logging
import os
from typing import Optional

from gpio.state import JukeboxState
from gpio.volume_control import VolumeControl

logger = logging.getLogger(__name__)


class GPIOMonitor:
    """GPIO button monitor with event callbacks"""
    
    def __init__(self, state: JukeboxState, player_service: Optional[object] = None):
        """
        Initialize GPIO monitor
        
        Args:
            state: JukeboxState instance
            player_service: PlayerService instance for triggering playback actions
        """
        self.state = state
        self.player_service = player_service
        self.buttons = {}
        self.pin_to_action = {}  # Map pin to action for release events
        self.running = False
        self.volume_control = None
        
        # Button configuration
        button_config = {
            17: {"name": "Play/Pause", "action": "toggle_play"},
            27: {"name": "Previous", "action": "previous"},
            22: {"name": "Next", "action": "next"},
            23: {"name": "Cycle Source", "action": "cycle_source"},
        }
        
        # Initialize buttons
        try:
            for pin, config in button_config.items():
                self.pin_to_action[pin] = config["action"]
                btn = Button(pin, pull_up=True, bounce_time=0.01)
                btn.when_pressed = lambda p=pin, a=config["action"], n=config["name"]: self._handle_press(p, a, n)
                btn.when_released = lambda p=pin: self._handle_release(p)
                self.buttons[pin] = btn
                logger.info(f"Initialized button on GPIO {pin}: {config['name']}")
        except Exception as e:
            logger.error(f"Error initializing GPIO buttons: {e}")
            logger.warning("Running in GPIO simulation mode (not on Raspberry Pi)")
            self.buttons = {}
        
        # Initialize rotary encoder volume control (ALSA PCM)
        try:
            # Get pins from environment or use defaults (KY-040: CLK=5, DT=6, SW=13)
            clk_pin = int(os.getenv('VOLUME_ENCODER_CLK_PIN', '5'))
            dt_pin = int(os.getenv('VOLUME_ENCODER_DT_PIN', '6'))
            sw_pin = os.getenv('VOLUME_ENCODER_SW_PIN', '13')
            sw_pin = int(sw_pin) if sw_pin else None
            throttle_ms = int(os.getenv('VOLUME_ENCODER_THROTTLE_MS', '50'))
            alsa_control = os.getenv('VOLUME_ENCODER_ALSA_CONTROL', 'PCM')
            volume_per_step = int(os.getenv('VOLUME_ENCODER_STEP', '2'))  # Default 2% per step
            
            self.volume_control = VolumeControl(
                player_service=None,  # Not needed for ALSA control
                clk_pin=clk_pin,
                dt_pin=dt_pin,
                sw_pin=sw_pin,
                update_throttle_ms=throttle_ms,
                alsa_control=alsa_control,
                volume_per_step=volume_per_step
            )
            logger.info("Volume rotary encoder initialized")
        except Exception as e:
            logger.warning(f"Could not initialize volume encoder: {e}")
            self.volume_control = None
    
    def _handle_press(self, pin: int, action: str, name: str):
        """Handle button press event - immediate state update for instant feedback"""
        self.state.add_event(pin, "pressed", action)
        
        # Update state immediately for instant user feedback
        if action == "toggle_play":
            self.state.toggle_play()
        elif action == "cycle_source":
            self.state.cycle_source()
        # Note: next/previous don't update state on press, only on release
    
    def _handle_release(self, pin: int):
        """Handle button release event - trigger player service action"""
        action = self.pin_to_action.get(pin)
        self.state.add_event(pin, "released", action or "")
        
        # Trigger player service action on release (non-blocking signal)
        if self.player_service and action:
            if action == "toggle_play":
                self.player_service.toggle_play()
            elif action == "next":
                self.player_service.next()
            elif action == "previous":
                self.player_service.previous()
            elif action == "cycle_source":
                self.player_service.cycle_source()
    
    def start(self):
        """Start GPIO monitoring"""
        self.running = True
        logger.info("GPIO monitor started")
    
    def stop(self):
        """Stop GPIO monitoring and cleanup"""
        self.running = False
        
        # Close volume control
        if self.volume_control:
            self.volume_control.close()
        
        # Close buttons
        for pin, btn in self.buttons.items():
            try:
                btn.close()
                logger.info(f"Closed button on GPIO {pin}")
            except Exception as e:
                logger.error(f"Error closing button on GPIO {pin}: {e}")

