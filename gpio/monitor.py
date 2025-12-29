"""GPIO button monitor with event callbacks"""

from gpiozero import Button
import logging

from gpio.state import JukeboxState

logger = logging.getLogger(__name__)


class GPIOMonitor:
    """GPIO button monitor with event callbacks"""
    
    def __init__(self, state: JukeboxState):
        self.state = state
        self.buttons = {}
        self.running = False
        
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
                btn = Button(pin, pull_up=True, bounce_time=0.1)
                btn.when_pressed = lambda p=pin, a=config["action"], n=config["name"]: self._handle_press(p, a, n)
                btn.when_released = lambda p=pin: self._handle_release(p)
                self.buttons[pin] = btn
                logger.info(f"Initialized button on GPIO {pin}: {config['name']}")
        except Exception as e:
            logger.error(f"Error initializing GPIO buttons: {e}")
            logger.warning("Running in GPIO simulation mode (not on Raspberry Pi)")
            self.buttons = {}
    
    def _handle_press(self, pin: int, action: str, name: str):
        """Handle button press event"""
        self.state.add_event(pin, "pressed", action)
        
        # Execute action
        if action == "toggle_play":
            self.state.toggle_play()
        elif action == "cycle_source":
            self.state.cycle_source()
        elif action == "previous":
            # TODO: Implement previous track logic
            logger.info("Previous track action triggered")
        elif action == "next":
            # TODO: Implement next track logic
            logger.info("Next track action triggered")
    
    def _handle_release(self, pin: int):
        """Handle button release event"""
        self.state.add_event(pin, "released", "")
    
    def start(self):
        """Start GPIO monitoring"""
        self.running = True
        logger.info("GPIO monitor started")
    
    def stop(self):
        """Stop GPIO monitoring and cleanup"""
        self.running = False
        for pin, btn in self.buttons.items():
            try:
                btn.close()
                logger.info(f"Closed button on GPIO {pin}")
            except Exception as e:
                logger.error(f"Error closing button on GPIO {pin}: {e}")

