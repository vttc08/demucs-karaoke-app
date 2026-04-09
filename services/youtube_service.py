"""YouTube service for search and download."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
from typing import List
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from adapters.ytdlp import YtDlpAdapter
from models import MediaItem, YouTubeSearchResult
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

    def search(
        self, query: str, max_results: int = 10, db: Session | None = None
    ) -> List[YouTubeSearchResult]:
        """
        Search YouTube for videos.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of search results
        """
        if db is None:
            youtube_results = self._search_results(query, max_results)
            local_results: List[dict] = []
        else:
            with ThreadPoolExecutor(max_workers=1) as executor:
                youtube_future = executor.submit(self._search_results, query, max_results)
                local_results = self._local_search(query, max_results, db)
                youtube_results = youtube_future.result()

        downloaded_ids = self._downloaded_video_ids(db, youtube_results)
        normalized_youtube = []
        for result in youtube_results:
            video_id = result.get("video_id")
            normalized_youtube.append(
                {
                    "source": "youtube",
                    "media_item_id": None,
                    "video_id": video_id,
                    "title": result.get("title") or "",
                    "channel": result.get("channel") or "",
                    "duration": result.get("duration"),
                    "thumbnail": result.get("thumbnail") or self._thumbnail_for_video_id(video_id),
                    "downloaded": bool(video_id and video_id in downloaded_ids),
                }
            )

        merged = self._merge_local_and_youtube(local_results, normalized_youtube)
        return [YouTubeSearchResult(**result) for result in merged[:max_results]]

    @staticmethod
    def _downloaded_video_ids(db: Session | None, results: List[dict]) -> set[str]:
        if db is None:
            return set()

        video_ids = [
            result.get("video_id")
            for result in results
            if isinstance(result.get("video_id"), str) and result.get("video_id")
        ]
        if not video_ids:
            return set()

        rows = (
            db.query(MediaItem.youtube_id, MediaItem.missing)
            .filter(MediaItem.youtube_id.in_(video_ids))
            .all()
        )
        return {
            youtube_id
            for youtube_id, missing in rows
            if youtube_id and not missing
        }

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

    @staticmethod
    def _thumbnail_for_video_id(video_id: str | None) -> str | None:
        if not video_id:
            return None
        return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    @staticmethod
    def _normalize_match_terms(query: str) -> List[str]:
        tokens = re.findall(r"[A-Za-z0-9]+", query.lower())
        return [token for token in tokens if token]

    def _local_search(self, query: str, max_results: int, db: Session) -> List[dict]:
        terms = self._normalize_match_terms(query)
        if not terms:
            return []

        match_query = " ".join(f"{term}*" for term in terms)
        try:
            rows = db.execute(
                text(
                    """
                    SELECT
                        m.id,
                        m.youtube_id,
                        m.title,
                        m.artist,
                        bm25(media_items_fts) AS rank
                    FROM media_items_fts
                    JOIN media_items AS m
                      ON m.id = media_items_fts.rowid
                    WHERE media_items_fts MATCH :match_query
                      AND m.missing = 0
                    ORDER BY rank ASC, m.updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"match_query": match_query, "limit": max_results},
            ).all()
        except OperationalError:
            return []

        local_results: List[dict] = []
        for row in rows:
            youtube_id = row.youtube_id or None
            local_results.append(
                {
                    "source": "local",
                    "media_item_id": int(row.id),
                    "video_id": youtube_id,
                    "title": row.title or "",
                    "channel": row.artist or "",
                    "duration": None,
                    "thumbnail": self._thumbnail_for_video_id(youtube_id),
                    "downloaded": True,
                }
            )
        return local_results

    @staticmethod
    def _result_identity_key(result: dict) -> tuple[str, str]:
        video_id = result.get("video_id")
        if isinstance(video_id, str) and video_id:
            return ("video_id", video_id.lower())

        title = " ".join(str(result.get("title") or "").lower().split())
        channel = " ".join(str(result.get("channel") or "").lower().split())
        return ("title_artist", f"{title}|{channel}")

    def _merge_local_and_youtube(
        self, local_results: List[dict], youtube_results: List[dict]
    ) -> List[dict]:
        merged: List[dict] = []
        seen_keys: set[tuple[str, str]] = set()

        for local_result in local_results:
            key = self._result_identity_key(local_result)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(local_result)

        for youtube_result in youtube_results:
            key = self._result_identity_key(youtube_result)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(youtube_result)

        return merged

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
