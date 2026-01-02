"""YouTube client using yt-dlp and mpv"""

import logging
import subprocess
import json
import os
from typing import Optional, List, Set
from pathlib import Path

logger = logging.getLogger(__name__)


class YouTubeClient:
    """Client for playing YouTube videos using yt-dlp and mpv"""
    
    def __init__(self, watched_videos_file: str = "watched_videos.json"):
        """
        Initialize YouTube client
        
        Args:
            watched_videos_file: Path to JSON file storing watched video IDs
        """
        self.current_process: Optional[subprocess.Popen] = None
        self.current_channel_url: Optional[str] = None
        self.current_videos: List[dict] = []  # List of videos from current channel
        self.current_video_index = 0
        self.watched_videos_file = Path(watched_videos_file)
        self.watched_videos: Set[str] = self._load_watched_videos()
        logger.info(f"YouTubeClient initialized (watched: {len(self.watched_videos)} videos)")
    
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
    
    def _get_channel_videos(self, channel_url: str, max_videos: int = 50) -> List[dict]:
        """
        Get list of videos from a YouTube channel using yt-dlp
        
        Args:
            channel_url: YouTube channel URL
            max_videos: Maximum number of videos to fetch
        
        Returns:
            List of video dictionaries with id, title, url
        """
        try:
            # Use yt-dlp to get channel videos
            cmd = [
                'yt-dlp',
                '--flat-playlist',
                '--print', '%(id)s|||%(title)s|||%(url)s',
                '--playlist-end', str(max_videos),
                channel_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            videos = []
            for line in result.stdout.strip().split('\n'):
                if '|||' in line:
                    parts = line.split('|||', 2)
                    if len(parts) == 3:
                        videos.append({
                            'id': parts[0],
                            'title': parts[1],
                            'url': parts[2]
                        })
            
            logger.info(f"Fetched {len(videos)} videos from channel")
            return videos
            
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
        
        # Start from current index and find unwatched video
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
    
    def play_channel(self, channel_url: str):
        """Get latest videos from channel and play first unwatched"""
        logger.info(f"YouTubeClient: Play channel '{channel_url}'")
        
        # Stop current playback
        self.stop()
        
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
            self.stop()
            
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
                check=True
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
            
            logger.info(f"Playing: {video['title']}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get video URL: {e.stderr}")
        except Exception as e:
            logger.error(f"Error playing video: {e}")
    
    def next(self):
        """Skip to next video (loops when all watched)"""
        logger.info("YouTubeClient: Next video command sent")
        
        if not self.current_videos:
            logger.warning("No videos available")
            return
        
        # Move to next video index
        self.current_video_index = (self.current_video_index + 1) % len(self.current_videos)
        video = self._get_next_unwatched_video()
        
        if video:
            self._play_video(video)
        else:
            logger.warning("No videos available")
    
    def previous(self):
        """Go to previous video"""
        logger.info("YouTubeClient: Previous video command sent")
        
        if not self.current_videos:
            logger.warning("No videos available")
            return
        
        # Move to previous video
        self.current_video_index = (self.current_video_index - 1) % len(self.current_videos)
        video = self.current_videos[self.current_video_index]
        self._play_video(video)
    
    def stop(self):
        """Stop playback"""
        logger.info("YouTubeClient: Stop command sent")
        
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
    
    def pause(self):
        """Pause playback (mpv doesn't support pause via signal, need IPC)"""
        logger.info("YouTubeClient: Pause command sent")
        # Note: mpv pause requires IPC socket. For now, stop/play
        # See: https://mpv.io/manual/stable/#json-ipc
        self.stop()
    
    def resume(self):
        """Resume playback"""
        logger.info("YouTubeClient: Resume command sent")
        # Resume by playing current video again
        if self.current_videos and 0 <= self.current_video_index < len(self.current_videos):
            video = self.current_videos[self.current_video_index]
            self._play_video(video)
