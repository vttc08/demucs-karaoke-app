"""YouTube service for search and download."""
from pathlib import Path
from typing import List
from adapters.ytdlp import YtDlpAdapter
from models import YouTubeSearchResult
from config import settings


class YouTubeService:
    """Service for YouTube operations."""

    def __init__(self):
        self.ytdlp = YtDlpAdapter()
        self.media_path = settings.media_path

    def search(self, query: str, max_results: int = 10) -> List[YouTubeSearchResult]:
        """
        Search YouTube for videos.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of search results
        """
        results = self.ytdlp.search(query, max_results)
        normalized = []
        for result in results:
            if not result.get("thumbnail") and result.get("video_id"):
                result = {
                    **result,
                    "thumbnail": (
                        f"https://i.ytimg.com/vi/{result['video_id']}/hqdefault.jpg"
                    ),
                }
            normalized.append(result)
        return [YouTubeSearchResult(**result) for result in normalized]

    def download_audio(self, youtube_id: str) -> Path:
        """
        Download audio from YouTube video.

        Args:
            youtube_id: YouTube video ID

        Returns:
            Path to downloaded audio file
        """
        return self.ytdlp.download_audio(youtube_id, self.media_path)

    def download_video(self, youtube_id: str) -> Path:
        """
        Download video from YouTube.

        Args:
            youtube_id: YouTube video ID

        Returns:
            Path to downloaded video file
        """
        return self.ytdlp.download_video(youtube_id, self.media_path)

    def download_video_with_audio(self, youtube_id: str) -> Path:
        """
        Download progressive video with audio for direct playback.

        Args:
            youtube_id: YouTube video ID

        Returns:
            Path to downloaded video file containing audio
        """
        return self.ytdlp.download_video_with_audio(youtube_id, self.media_path)
