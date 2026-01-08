"""YouTube client wrapper for YouTubeThread"""

import logging
from player.youtube_thread import YouTubeThread, YouTubeCommand, YouTubeCommandType
from gpio.state import JukeboxState

logger = logging.getLogger(__name__)


class YouTubeClient:
    """Client for playing YouTube videos - wraps YouTubeThread"""
    
    def __init__(self, state: JukeboxState, watched_videos: set = None, watched_videos_file: str = "data/watched_videos.json"):
        """
        Initialize YouTube client
        
        Args:
            state: JukeboxState instance for coordination
            watched_videos: Pre-loaded set of watched video IDs (optional)
            watched_videos_file: Path to JSON file storing watched video IDs
        """
        self.state = state
        self.youtube_thread = YouTubeThread(state, watched_videos, watched_videos_file)
        logger.info("YouTubeClient initialized")
    
    def start(self):
        """Start the YouTube thread"""
        if not self.youtube_thread.is_alive():
            self.youtube_thread.start()
            logger.info("YouTubeThread started")
    
    def stop_thread(self):
        """Stop the YouTube thread gracefully"""
        if self.youtube_thread.is_alive():
            self.youtube_thread.stop_thread()
            logger.info("YouTubeThread stopped")
    
    def play_channel(self, channel_url: str):
        """Get latest videos from channel and play first unwatched"""
        logger.info(f"YouTubeClient: Play channel '{channel_url}'")
        command = YouTubeCommand(
            YouTubeCommandType.PLAY_CHANNEL,
            {"channel_url": channel_url}
        )
        self.youtube_thread.send_command(command)
    
    def next(self):
        """Skip to next video"""
        logger.info("YouTubeClient: Next video command sent")
        command = YouTubeCommand(YouTubeCommandType.NEXT)
        self.youtube_thread.send_command(command)
    
    def previous(self):
        """Go to previous video"""
        logger.info("YouTubeClient: Previous video command sent")
        command = YouTubeCommand(YouTubeCommandType.PREVIOUS)
        self.youtube_thread.send_command(command)
    
    def stop(self):
        """Stop playback"""
        logger.info("YouTubeClient: Stop command sent")
        command = YouTubeCommand(YouTubeCommandType.STOP)
        self.youtube_thread.send_command(command)
    
    def pause(self):
        """Pause playback"""
        logger.info("YouTubeClient: Pause command sent")
        command = YouTubeCommand(YouTubeCommandType.PAUSE)
        self.youtube_thread.send_command(command)
    
    def resume(self):
        """Resume playback"""
        logger.info("YouTubeClient: Resume command sent")
        command = YouTubeCommand(YouTubeCommandType.RESUME)
        self.youtube_thread.send_command(command)
