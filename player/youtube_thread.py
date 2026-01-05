"""YouTube thread for managing mpv playback and yt-dlp operations"""

import threading
import queue
import subprocess
import json
import logging
import time
import urllib.request
import xml.etree.ElementTree as ET
import re
from typing import Optional, List, Set
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class YouTubeCommandType(Enum):
    """Command types for YouTube thread"""
    PLAY_CHANNEL = "play_channel"
    NEXT = "next"
    PREVIOUS = "previous"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    SHUTDOWN = "shutdown"


@dataclass
class YouTubeCommand:
    """Command to send to YouTube thread"""
    type: YouTubeCommandType
    data: Optional[dict] = None


class YouTubeThread(threading.Thread):
    """Thread for managing YouTube playback with mpv"""
    
    def __init__(self, state, watched_videos_file: str = "watched_videos.json"):
        """
        Initialize YouTube thread
        
        Args:
            state: JukeboxState instance for state synchronization
            watched_videos_file: Path to JSON file storing watched video IDs
        """
        super().__init__(name="YouTubeThread", daemon=True)
        self.state = state
        self.watched_videos_file = Path(watched_videos_file)
        self.watched_videos: Set[str] = self._load_watched_videos()
        
        self.command_queue = queue.Queue()
        self.current_process: Optional[subprocess.Popen] = None
        self.current_channel_url: Optional[str] = None
        self.current_videos: List[dict] = []
        self.current_video_index = 0
        self.running = False
        
        logger.info(f"YouTubeThread initialized (watched: {len(self.watched_videos)} videos)")
    
    def _load_watched_videos(self) -> Set[str]:
        """Load watched video IDs from file"""
        if self.watched_videos_file.exists():
            try:
                with open(self.watched_videos_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('watched', []))
            except Exception as e:
                logger.warning(f"Failed to load watched videos: {e}")
        return set()
    
    def _save_watched_videos(self):
        """Save watched video IDs to file"""
        try:
            with open(self.watched_videos_file, 'w') as f:
                json.dump({'watched': list(self.watched_videos)}, f)
        except Exception as e:
            logger.error(f"Failed to save watched videos: {e}")
    
    def run(self):
        """Main thread loop - handles commands and process monitoring"""
        self.running = True
        logger.info("YouTubeThread started")
        
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
                logger.error(f"YouTubeThread error: {e}", exc_info=True)
                time.sleep(1.0)
        
        # Cleanup
        self._stop_playback()
        logger.info("YouTubeThread stopped")
    
    def _monitor_process(self):
        """Monitor mpv process and handle completion"""
        if self.current_process:
            # Check if process has finished
            poll_result = self.current_process.poll()
            if poll_result is not None:
                # Process finished
                logger.info(f"mpv process finished with code {poll_result}")
                self.current_process = None
                
                # Update state
                with self.state.lock:
                    self.state.is_playing = False
                
                # Auto-play next video if available
                if self.current_videos:
                    self._play_next_video()
    
    def _process_command(self, command: YouTubeCommand):
        """Process a command from the queue"""
        try:
            if command.type == YouTubeCommandType.PLAY_CHANNEL:
                channel_url = command.data.get("channel_url") if command.data else None
                if channel_url:
                    self._play_channel(channel_url)
            elif command.type == YouTubeCommandType.NEXT:
                self._next_video()
            elif command.type == YouTubeCommandType.PREVIOUS:
                self._previous_video()
            elif command.type == YouTubeCommandType.STOP:
                self._stop_playback()
            elif command.type == YouTubeCommandType.PAUSE:
                self._pause_playback()
            elif command.type == YouTubeCommandType.RESUME:
                self._resume_playback()
            elif command.type == YouTubeCommandType.SHUTDOWN:
                self.running = False
            else:
                logger.warning(f"Unknown command type: {command.type}")
        except Exception as e:
            logger.error(f"Error processing command {command.type.value}: {e}")
    
    def _get_channel_id(self, channel_url: str) -> Optional[str]:
        """Extract or fetch channel ID from various YouTube URL formats"""
        # Direct channel ID URL: https://www.youtube.com/channel/CHANNEL_ID
        channel_id_match = re.search(r'youtube\.com/channel/([a-zA-Z0-9_-]+)', channel_url)
        if channel_id_match:
            return channel_id_match.group(1)
        
        # For other formats (@handle, /c/, /user/), use yt-dlp to get channel ID
        try:
            cmd = [
                'yt-dlp',
                '--flat-playlist',
                '--print', '%(channel_id)s',
                '--playlist-end', '1',
                channel_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            
            channel_id = result.stdout.strip()
            if channel_id:
                return channel_id
        except Exception as e:
            logger.warning(f"Failed to get channel ID from URL: {e}")
        
        return None
    
    def _get_channel_videos(self, channel_url: str, max_videos: int = 50) -> List[dict]:
        """Get list of videos from a YouTube channel using RSS feed"""
        try:
            # Get channel ID
            channel_id = self._get_channel_id(channel_url)
            if not channel_id:
                logger.error(f"Could not extract channel ID from: {channel_url}")
                return []
            
            # Fetch RSS feed
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            logger.debug(f"Fetching RSS feed from: {rss_url}")
            
            with urllib.request.urlopen(rss_url, timeout=10) as response:
                rss_data = response.read()
            
            # Parse RSS XML
            root = ET.fromstring(rss_data)
            
            # Namespace for YouTube RSS
            ns = {'yt': 'http://www.youtube.com/xml/schemas/2015',
                  'media': 'http://search.yahoo.com/mrss/',
                  'atom': 'http://www.w3.org/2005/Atom'}
            
            videos = []
            entries = root.findall('atom:entry', ns)
            
            for entry in entries[:max_videos]:
                try:
                    # Get video ID from yt:videoId
                    video_id_elem = entry.find('yt:videoId', ns)
                    if video_id_elem is None:
                        continue
                    video_id = video_id_elem.text
                    
                    # Get title
                    title_elem = entry.find('atom:title', ns)
                    title = title_elem.text if title_elem is not None else "Unknown"
                    
                    # Get video URL
                    link_elem = entry.find('atom:link', ns)
                    video_url = link_elem.get('href') if link_elem is not None else f"https://www.youtube.com/watch?v={video_id}"
                    
                    videos.append({
                        'id': video_id,
                        'title': title,
                        'url': video_url
                    })
                except Exception as e:
                    logger.warning(f"Error parsing video entry: {e}")
                    continue
            
            logger.info(f"Fetched {len(videos)} videos from channel via RSS")
            return videos
            
        except urllib.error.URLError as e:
            logger.error(f"Failed to fetch RSS feed: {e}")
            return []
        except ET.ParseError as e:
            logger.error(f"Failed to parse RSS feed: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching channel videos: {e}")
            return []
    
    def _get_next_unwatched_video(self) -> Optional[dict]:
        """Get next unwatched video from current channel"""
        if not self.current_videos:
            return None
        
        for i in range(len(self.current_videos)):
            idx = (self.current_video_index + i) % len(self.current_videos)
            video = self.current_videos[idx]
            if video['id'] not in self.watched_videos:
                self.current_video_index = idx
                return video
        
        # All videos watched, reset and return first (looping behavior)
        logger.info("All videos watched, resetting to beginning")
        self.current_video_index = 0
        if self.current_videos:
            return self.current_videos[0]
        return None
    
    def _play_channel(self, channel_url: str):
        """Get latest videos from channel and play first unwatched"""
        logger.info(f"YouTubeThread: Play channel '{channel_url}'")
        
        # Stop current playback
        self._stop_playback()
        
        # Fetch videos from channel
        self.current_channel_url = channel_url
        self.current_videos = self._get_channel_videos(channel_url)
        self.current_video_index = 0
        
        if not self.current_videos:
            logger.error("No videos found in channel")
            return
        
        # Get and play first unwatched video
        video = self._get_next_unwatched_video()
        if video:
            self._play_video(video)
    
    def _play_video(self, video: dict):
        """Play a video using mpv"""
        try:
            # Stop any existing playback
            self._stop_playback()
            
            # Get video URL using yt-dlp (best audio quality)
            cmd = [
                'yt-dlp',
                '-f', 'bestaudio/best',
                '-g',  # Get URL only
                video['url']
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            
            video_url = result.stdout.strip()
            
            # Play with mpv (no video, audio only)
            self.current_process = subprocess.Popen(
                ['mpv', '--no-video', '--really-quiet', video_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Mark as watched
            self.watched_videos.add(video['id'])
            self._save_watched_videos()
            
            # Update state
            with self.state.lock:
                self.state.is_playing = True
                self.state.current_track = {
                    "title": video['title'],
                    "artist": "YouTube",
                    "album": "",
                    "uri": video['url']
                }
            
            logger.info(f"Playing: {video['title']}")
            
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp command timed out")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get video URL: {e.stderr}")
        except Exception as e:
            logger.error(f"Error playing video: {e}")
    
    def _play_next_video(self):
        """Play next video (called automatically when current finishes)"""
        if not self.current_videos:
            return
        
        self.current_video_index = (self.current_video_index + 1) % len(self.current_videos)
        video = self._get_next_unwatched_video()
        
        if video:
            self._play_video(video)
    
    def _next_video(self):
        """Skip to next video (manual command)"""
        logger.info("YouTubeThread: Next video command sent")
        
        if not self.current_videos:
            logger.warning("No videos available")
            return
        
        self._play_next_video()
    
    def _previous_video(self):
        """Go to previous video"""
        logger.info("YouTubeThread: Previous video command sent")
        
        if not self.current_videos:
            logger.warning("No videos available")
            return
        
        # Move to previous video
        self.current_video_index = (self.current_video_index - 1) % len(self.current_videos)
        video = self.current_videos[self.current_video_index]
        self._play_video(video)
    
    def _stop_playback(self):
        """Stop playback"""
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
        
        # Update state
        with self.state.lock:
            self.state.is_playing = False
    
    def _pause_playback(self):
        """Pause playback"""
        logger.info("YouTubeThread: Pause command sent")
        # mpv pause requires IPC socket. For now, stop/play
        self._stop_playback()
        with self.state.lock:
            self.state.is_playing = False
    
    def _resume_playback(self):
        """Resume playback"""
        logger.info("YouTubeThread: Resume command sent")
        # Resume by playing current video again
        if self.current_videos and 0 <= self.current_video_index < len(self.current_videos):
            video = self.current_videos[self.current_video_index]
            self._play_video(video)
    
    def send_command(self, command: YouTubeCommand):
        """Send a command to the thread (non-blocking)"""
        try:
            self.command_queue.put_nowait(command)
        except queue.Full:
            logger.warning("YouTube command queue full, dropping command")
    
    def stop_thread(self):
        """Stop the thread gracefully"""
        self.running = False
        self.send_command(YouTubeCommand(YouTubeCommandType.SHUTDOWN))
        self.join(timeout=5.0)
        if self.is_alive():
            logger.warning("YouTubeThread did not stop gracefully")

