"""YouTube thread for managing mpv playback and yt-dlp operations"""

import threading
import queue
import subprocess
import json
import logging
import time
import re
from typing import Optional, List, Set
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from db.models import WatchedVideo as WatchedVideoModel
from db.database import AsyncSessionLocal, run_async

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
    
    def __init__(self, state, watched_videos_file: str = "data/watched_videos.json"):
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
        """Load watched video IDs from database, fallback to file"""
        try:
            return self._load_watched_videos_from_db_sync()
        except Exception as e:
            logger.warning(f"Failed to load watched videos from database: {e}, trying file fallback")
            return self._load_watched_videos_from_file()
    
    def _load_watched_videos_from_file(self) -> Set[str]:
        """Load watched video IDs from file (fallback)"""
        if self.watched_videos_file.exists():
            try:
                with open(self.watched_videos_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('watched', []))
            except Exception as e:
                logger.warning(f"Failed to load watched videos from file: {e}")
        return set()
    
    async def _load_watched_videos_from_db(self) -> Set[str]:
        """Load watched video IDs from database
        
        Note: This loads all video IDs into memory for fast O(1) set lookups.
        For very large datasets (10k+ videos), consider lazy loading or caching strategies.
        """
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            # Uses index on video_id for efficient query
            result = await session.execute(select(WatchedVideoModel.video_id))
            video_ids = result.scalars().all()
            return set(video_ids)
    
    async def _is_video_watched_in_db(self, video_id: str) -> bool:
        """Check if a single video is watched in database (O(log n) lookup with index)
        
        This is more efficient than loading all IDs for single checks.
        Useful for lazy loading strategies with large datasets.
        """
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select, exists
            result = await session.execute(
                select(exists().where(WatchedVideoModel.video_id == video_id))
            )
            return result.scalar() or False
    
    def _load_watched_videos_from_db_sync(self) -> Set[str]:
        """Sync wrapper for loading watched videos from database"""
        return run_async(self._load_watched_videos_from_db())
    
    def _save_watched_videos(self):
        """Save watched video IDs to database, fallback to file"""
        try:
            self._save_watched_videos_to_db_sync()
        except Exception as e:
            logger.warning(f"Failed to save watched videos to database: {e}, trying file fallback")
            self._save_watched_videos_to_file()
    
    def _save_watched_videos_to_file(self):
        """Save watched video IDs to file (fallback)"""
        try:
            with open(self.watched_videos_file, 'w') as f:
                json.dump({'watched': list(self.watched_videos)}, f)
        except Exception as e:
            logger.error(f"Failed to save watched videos to file: {e}")
    
    async def _save_watched_videos_to_db(self):
        """Save watched video IDs to database (batch upsert)"""
        if not self.watched_videos:
            return
        
        async with AsyncSessionLocal() as session:
            from sqlalchemy.dialects.postgresql import insert
            
            # Direct bulk insert - let database handle duplicates via ON CONFLICT
            # This is more efficient than pre-checking all existing IDs
            # The unique index on video_id ensures no duplicates
            stmt = insert(WatchedVideoModel).values([
                {'video_id': video_id} for video_id in self.watched_videos
            ])
            # Use ON CONFLICT DO NOTHING for idempotency (handles duplicates efficiently)
            stmt = stmt.on_conflict_do_nothing(index_elements=['video_id'])
            result = await session.execute(stmt)
            await session.commit()
            
            # Log how many were actually inserted (result.rowcount shows affected rows)
            # Note: rowcount may not be accurate for ON CONFLICT, but it's informative
            logger.debug(f"Upserted watched video IDs to database (total in memory: {len(self.watched_videos)})")
    
    def _save_watched_videos_to_db_sync(self):
        """Sync wrapper for saving watched videos to database"""
        run_async(self._save_watched_videos_to_db())
    
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
        """Get list of videos from a YouTube channel using yt-dlp"""
        try:
            # Normalize channel URL (fix double @ if present)
            normalized_url = channel_url.replace('@@', '@')
            
            # Use yt-dlp to get channel videos
            # Format: %(id)s|%(title)s
            # Note: %(url)s is not reliable with --flat-playlist, so we construct it from ID
            cmd = [
                'yt-dlp',
                '--flat-playlist',
                '--print', '%(id)s|%(title)s',
                '--playlist-end', str(max_videos),
                normalized_url
            ]
            
            logger.debug(f"Fetching videos from channel: {normalized_url}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            
            videos = []
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                
                try:
                    # Parse format: video_id|title
                    parts = line.split('|', 1)
                    if len(parts) >= 2:
                        video_id = parts[0].strip()
                        title = parts[1].strip()
                    elif len(parts) == 1:
                        # Just video ID, no title
                        video_id = parts[0].strip()
                        title = "Unknown"
                    else:
                        # Skip empty lines
                        continue
                    
                    # Construct URL from video ID (more reliable than using %(url)s)
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    
                    videos.append({
                        'id': video_id,
                        'title': title,
                        'url': video_url
                    })
                except Exception as e:
                    logger.warning(f"Error parsing video line '{line}': {e}")
                    continue
            
            logger.info(f"Fetched {len(videos)} videos from channel via yt-dlp")
            return videos
            
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp command timed out while fetching channel videos")
            return []
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch channel videos: {e.stderr}")
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

