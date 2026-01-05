"""Announcement thread for managing text-to-speech announcements with Piper TTS"""

import threading
import queue
import subprocess
import logging
import time
import hashlib
from typing import Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AnnouncementCommandType(Enum):
    """Command types for announcement thread"""
    ANNOUNCE = "announce"
    SHUTDOWN = "shutdown"


@dataclass
class AnnouncementCommand:
    """Command to send to announcement thread"""
    type: AnnouncementCommandType
    data: Optional[dict] = None


class AnnouncementThread(threading.Thread):
    """Thread for managing TTS announcements with Piper and mpv playback"""
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        voice_model_path: Optional[str] = None
    ):
        """
        Initialize announcement thread
        
        Args:
            cache_dir: Directory for caching audio files. Defaults to data/piper/ relative to project root
            voice_model_path: Path to Piper voice model file. If None, will try to find or download
        """
        super().__init__(name="AnnouncementThread", daemon=True)
        
        # Set up cache directory
        if cache_dir is None:
            # Default to data/piper/ relative to project root
            project_root = Path(__file__).parent.parent
            cache_dir = str(project_root / "data" / "piper")
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Voice model path
        self.voice_model_path = voice_model_path
        
        self.command_queue = queue.Queue()
        self.current_process: Optional[subprocess.Popen] = None
        self.running = False
        
        logger.info(f"AnnouncementThread initialized (cache_dir={self.cache_dir})")
    
    def run(self):
        """Main thread loop - handles commands and process monitoring"""
        self.running = True
        logger.info("AnnouncementThread started")
        
        while self.running:
            try:
                # Process commands (non-blocking with timeout)
                try:
                    command = self.command_queue.get(timeout=0.1)
                    self._process_command(command)
                except queue.Empty:
                    pass
                
                # Monitor mpv process
                self._monitor_process()
                
                # Small sleep to prevent tight loop
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"AnnouncementThread error: {e}", exc_info=True)
                time.sleep(1.0)
        
        # Cleanup
        self._stop_playback()
        logger.info("AnnouncementThread stopped")
    
    def _monitor_process(self):
        """Monitor mpv process and handle completion"""
        if self.current_process:
            # Check if process has finished
            poll_result = self.current_process.poll()
            if poll_result is not None:
                # Process finished
                logger.debug(f"mpv process finished with code {poll_result}")
                self.current_process = None
    
    def _process_command(self, command: AnnouncementCommand):
        """Process a command from the queue"""
        try:
            if command.type == AnnouncementCommandType.ANNOUNCE:
                text = command.data.get("text") if command.data else None
                if text:
                    self._announce(text)
                else:
                    logger.warning("Announce command missing text")
            elif command.type == AnnouncementCommandType.SHUTDOWN:
                self.running = False
            else:
                logger.warning(f"Unknown command type: {command.type}")
        except Exception as e:
            logger.error(f"Error processing command {command.type.value}: {e}")
    
    def _get_cache_path(self, text: str) -> Path:
        """
        Get cache file path for given text
        
        Args:
            text: Text to generate hash for
            
        Returns:
            Path to cache file
        """
        # Generate SHA256 hash of text
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        return self.cache_dir / f"{text_hash}.wav"
    
    def _generate_audio(self, text: str) -> Optional[Path]:
        """
        Generate audio file for text using Piper TTS
        
        Args:
            text: Text to convert to speech
            
        Returns:
            Path to audio file, or None if generation failed
        """
        cache_path = self._get_cache_path(text)
        
        # Check if cached file exists
        if cache_path.exists():
            logger.debug(f"Using cached audio for text: {text[:50]}...")
            return cache_path
        
        # Need to generate audio
        logger.info(f"Generating audio for text: {text[:50]}...")
        
        # Try to use piper command (system installation)
        # First check if we have a voice model
        if not self.voice_model_path:
            logger.error("Voice model path not configured. Cannot generate audio.")
            logger.info("Please configure voice_model_path or install a Piper voice model.")
            return None
        
        if not Path(self.voice_model_path).exists():
            logger.error(f"Voice model not found at {self.voice_model_path}")
            logger.info("Please download a voice model from https://github.com/rhasspy/piper/releases")
            return None
        
        try:
            # Generate audio using piper command
            # Pass text via stdin instead of --text flag to avoid issues
            # Note: Old cached files may contain "text" word due to --text flag bug
            cmd = [
                'piper',
                '--model', self.voice_model_path,
                '--output_file', str(cache_path)
            ]
            
            # Log the text being sent to Piper for debugging
            logger.debug(f"Sending text to Piper: '{text}'")
            
            result = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            
            if cache_path.exists():
                logger.info(f"Successfully generated audio: {cache_path}")
                return cache_path
            else:
                logger.error("Piper command succeeded but output file not found")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("Piper command timed out")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"Piper command failed: {e.stderr}")
            return None
        except FileNotFoundError:
            logger.error("piper command not found. Please install piper-tts or piper system package.")
            logger.info("Install with: pip install piper-tts or system package manager")
            return None
        except Exception as e:
            logger.error(f"Error generating audio: {e}")
            return None
    
    def _play_audio(self, audio_path: Path):
        """
        Play audio file using mpv
        
        Args:
            audio_path: Path to audio file to play
        """
        try:
            # Stop any existing playback (interrupt capability)
            self._stop_playback()
            
            if not audio_path.exists():
                logger.error(f"Audio file not found: {audio_path}")
                return
            
            # Play with mpv (no video, audio only)
            self.current_process = subprocess.Popen(
                ['mpv', '--no-video', '--really-quiet', str(audio_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            logger.info(f"Playing announcement: {audio_path.name}")
            
        except FileNotFoundError:
            logger.error("mpv not found. Please install mpv: sudo apt-get install mpv")
        except Exception as e:
            logger.error(f"Error playing audio: {e}")
    
    def _stop_playback(self):
        """Stop current playback"""
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
            except Exception as e:
                logger.error(f"Error stopping playback: {e}")
            finally:
                self.current_process = None
    
    def _announce(self, text: str):
        """
        Announce text (generate audio and play)
        
        Args:
            text: Text to announce
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for announcement")
            return
        
        # Log the actual text being passed (for debugging)
        logger.info(f"Announcing text: '{text}'")
        
        # Generate or get cached audio
        audio_path = self._generate_audio(text)
        
        if audio_path:
            # Play the audio
            self._play_audio(audio_path)
        else:
            logger.warning(f"Failed to generate audio for announcement: {text[:50]}...")
    
    def send_command(self, command: AnnouncementCommand):
        """Send a command to the thread (non-blocking)"""
        try:
            self.command_queue.put_nowait(command)
        except queue.Full:
            logger.warning("Announcement command queue full, dropping command")
    
    def stop_thread(self):
        """Stop the thread gracefully"""
        self.running = False
        self.send_command(AnnouncementCommand(AnnouncementCommandType.SHUTDOWN))
        self.join(timeout=5.0)
        if self.is_alive():
            logger.warning("AnnouncementThread did not stop gracefully")

