#!/usr/bin/env python3
"""Test script for rotary encoder volume control"""

import logging
import time
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from gpio import JukeboxState
from gpio.volume_control import VolumeControl
from player import PlayerService

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set GPIO logger to INFO for testing
logging.getLogger("gpio").setLevel(logging.INFO)


# No mock needed - VolumeControl now uses ALSA directly


def test_volume_encoder():
    """Test the rotary encoder volume control"""
    logger.info("Starting rotary encoder ALSA PCM volume control test...")
    logger.info("Rotate the encoder to change ALSA PCM volume")
    logger.info("Press Ctrl+C to exit")
    
    # Get pins from environment or use defaults (KY-040: CLK=5, DT=6, SW=13)
    import os
    clk_pin = int(os.getenv('VOLUME_ENCODER_CLK_PIN', '5'))
    dt_pin = int(os.getenv('VOLUME_ENCODER_DT_PIN', '6'))
    sw_pin = os.getenv('VOLUME_ENCODER_SW_PIN', '13')
    sw_pin = int(sw_pin) if sw_pin else None
    alsa_control = os.getenv('VOLUME_ENCODER_ALSA_CONTROL', 'PCM')
    volume_per_step = int(os.getenv('VOLUME_ENCODER_STEP', '2'))  # Default 2% per step
    
    logger.info(f"Using GPIO pins: CLK={clk_pin}, DT={dt_pin}, SW={sw_pin}")
    logger.info(f"Controlling ALSA control: {alsa_control}")
    logger.info(f"Volume change per step: {volume_per_step}%")
    
    try:
        # Initialize volume control (no player_service needed for ALSA)
        volume_control = VolumeControl(
            player_service=None,  # Not needed for ALSA control
            clk_pin=clk_pin,
            dt_pin=dt_pin,
            sw_pin=sw_pin,
            update_throttle_ms=50,
            alsa_control=alsa_control,
            volume_per_step=volume_per_step
        )
        
        if not volume_control.encoder:
            logger.error("Failed to initialize encoder. Check GPIO pins and hardware.")
            return
        
        logger.info("Rotary encoder initialized successfully!")
        logger.info("Rotate the encoder clockwise to increase ALSA PCM volume")
        logger.info("Rotate the encoder counter-clockwise to decrease ALSA PCM volume")
        if sw_pin:
            logger.info("Press the encoder button to mute/unmute")
        logger.info("")
        
        # Monitor volume changes from ALSA
        last_volume = volume_control._get_alsa_volume()
        if last_volume is not None:
            logger.info(f"Current ALSA {alsa_control} volume: {last_volume}%")
        
        while True:
            current_volume = volume_control._get_alsa_volume()
            if current_volume is not None and current_volume != last_volume:
                logger.info(f"ALSA {alsa_control} volume: {current_volume}%")
                last_volume = current_volume
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)
    finally:
        if 'volume_control' in locals():
            volume_control.close()
        logger.info("Test completed")


if __name__ == "__main__":
    test_volume_encoder()


