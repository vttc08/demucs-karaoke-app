"""Lyrics lookup service."""
from typing import Optional
import httpx


class LyricsService:
    """Service for fetching lyrics from external sources."""

    def __init__(self):
        self.base_url = "https://lrclib.net"

    async def fetch_lyrics(self, title: str, artist: Optional[str] = None) -> Optional[str]:
        """
        Fetch lyrics for a song.

        Args:
            title: Song title
            artist: Artist name (optional)

        Returns:
            Lyrics text or None if not found
        """
        query = title.strip()
        if artist and artist.strip():
            query = f"{title.strip()} {artist.strip()}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/search",
                params={"q": query},
            )
            response.raise_for_status()
            results = response.json()

        if not isinstance(results, list):
            return None

        normalized_title = title.lower().strip()
        normalized_artist = (artist or "").lower().strip()
        best_entry = None

        for entry in results:
            if not isinstance(entry, dict):
                continue
            track_name = str(entry.get("trackName", "")).lower().strip()
            artist_name = str(entry.get("artistName", "")).lower().strip()
            if normalized_title and normalized_title in track_name:
                if not normalized_artist or normalized_artist in artist_name:
                    best_entry = entry
                    break
            if best_entry is None:
                best_entry = entry

        if not best_entry:
            return None

        synced = best_entry.get("syncedLyrics")
        if isinstance(synced, str) and synced.strip():
            return synced

        plain = best_entry.get("plainLyrics")
        if isinstance(plain, str) and plain.strip():
            return plain

        return None

    def parse_lyrics_to_lines(self, lyrics: str) -> list[str]:
        """
        Parse lyrics text into individual lines.

        Args:
            lyrics: Raw lyrics text

        Returns:
            List of lyric lines
        """
        return [line.strip() for line in lyrics.split("\n") if line.strip()]
