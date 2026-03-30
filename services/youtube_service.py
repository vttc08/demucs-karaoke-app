"""YouTube service for search and download."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
from typing import List
from adapters.ytdlp import YtDlpAdapter
from models import YouTubeSearchResult
from config import settings


class YouTubeService:
    """Service for YouTube operations."""

    YOUTUBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
    YOUTUBE_URL_PATTERN = re.compile(
        r"^(https?://)?(www\.)?(youtube\.com/watch\?[^ ]*v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        re.IGNORECASE,
    )

    def __init__(self):
        self.ytdlp = YtDlpAdapter()

    @staticmethod
    def _media_path() -> Path:
        return settings.media_path

    def search(self, query: str, max_results: int = 10) -> List[YouTubeSearchResult]:
        """
        Search YouTube for videos.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of search results
        """
        results = self._search_results(query, max_results)
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

    def _search_results(self, query: str, max_results: int) -> List[dict]:
        """Search with optional concurrent karaoke query strategy."""
        youtube_url = self._extract_youtube_url(query)
        if youtube_url:
            return [self.ytdlp.get_video_info(youtube_url)]

        if not settings.concurrent_ytdlp_search_enabled:
            return self.ytdlp.search(query, max_results)
        if "karaoke" in query.lower():
            return self.ytdlp.search(query, max_results)

        karaoke_query = f"{query} karaoke"
        with ThreadPoolExecutor(max_workers=2) as executor:
            base_future = executor.submit(self.ytdlp.search, query, max_results)
            karaoke_future = executor.submit(self.ytdlp.search, karaoke_query, max_results)
            base_results = base_future.result()
            karaoke_results = karaoke_future.result()
        merged = self._stagger_and_dedupe(base_results, karaoke_results)
        return merged[:max_results]

    @classmethod
    def _extract_youtube_url(cls, query: str) -> str | None:
        """Return normalized YouTube URL when query looks like a YouTube link."""
        text = query.strip()
        if not text:
            return None
        if cls.YOUTUBE_ID_PATTERN.match(text):
            return f"https://www.youtube.com/watch?v={text}"
        match = cls.YOUTUBE_URL_PATTERN.search(text)
        if not match:
            return None
        url = text
        if not url.lower().startswith(("http://", "https://")):
            url = f"https://{url}"
        return url

    @staticmethod
    def _stagger_and_dedupe(base_results: List[dict], karaoke_results: List[dict]) -> List[dict]:
        """Interleave base/karaoke lists and dedupe by video_id preserving order."""
        merged: List[dict] = []
        max_len = max(len(base_results), len(karaoke_results))
        for index in range(max_len):
            if index < len(base_results):
                merged.append(base_results[index])
            if index < len(karaoke_results):
                merged.append(karaoke_results[index])

        deduped: List[dict] = []
        seen_video_ids = set()
        for item in merged:
            video_id = item.get("video_id")
            if video_id and video_id in seen_video_ids:
                continue
            if video_id:
                seen_video_ids.add(video_id)
            deduped.append(item)
        return deduped

    def download_audio(self, youtube_id: str) -> Path:
        """
        Download audio from YouTube video.

        Args:
            youtube_id: YouTube video ID

        Returns:
            Path to downloaded audio file
        """
        return self.ytdlp.download_audio(youtube_id, self._media_path())

    def download_video(self, youtube_id: str) -> Path:
        """
        Download video from YouTube.

        Args:
            youtube_id: YouTube video ID

        Returns:
            Path to downloaded video file
        """
        return self.ytdlp.download_video(youtube_id, self._media_path())

    def download_video_with_audio(self, youtube_id: str) -> Path:
        """
        Download progressive video with audio for direct playback.

        Args:
            youtube_id: YouTube video ID

        Returns:
            Path to downloaded video file containing audio
        """
        return self.ytdlp.download_video_with_audio(youtube_id, self._media_path())
