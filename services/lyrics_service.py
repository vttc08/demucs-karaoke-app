"""Lyrics lookup and parsing service."""
import json
import math
import re
from pathlib import Path
from typing import Optional
import httpx
from config import settings

_TIMESTAMP_PATTERN = re.compile(r"\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]")
_OFFSET_TAG_PATTERN = re.compile(r"^\[offset:([+-]?\d+)\]\s*$", re.IGNORECASE)


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

    def parse_lrc_to_cues(self, lyrics: str) -> list[dict[str, float | str]]:
        """Parse LRC into sorted cue objects."""
        offset_ms = 0
        cues: list[dict[str, float | str]] = []

        for raw_line in lyrics.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            offset_match = _OFFSET_TAG_PATTERN.fullmatch(line)
            if offset_match is not None:
                offset_ms = int(offset_match.group(1))
                continue

            timestamps = list(_TIMESTAMP_PATTERN.finditer(line))
            if not timestamps:
                continue

            text = _TIMESTAMP_PATTERN.sub("", line).strip()
            if not text:
                continue

            for match in timestamps:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                if seconds >= 60:
                    continue

                fraction_raw = match.group(3)
                fraction = 0.0
                if fraction_raw:
                    fraction = int(fraction_raw) / (10 ** len(fraction_raw))

                total_seconds = minutes * 60 + seconds + fraction + (offset_ms / 1000)
                if total_seconds < 0:
                    continue

                cues.append({"time": total_seconds, "text": text})

        cues.sort(key=lambda cue: float(cue["time"]))
        return cues

    def parse_json_to_cues(self, payload: str) -> list[dict[str, float | str]]:
        """Parse JSON lyrics cues and normalize their shape."""
        data = json.loads(payload)
        rows = data.get("cues") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("JSON lyrics payload must be a list or {\"cues\": [...]} object")

        cues: list[dict[str, float | str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            raw_time = row.get("time", row.get("start", row.get("timestamp")))
            if not isinstance(raw_time, (int, float)):
                continue

            timestamp = float(raw_time)
            if not math.isfinite(timestamp):
                continue

            raw_text = row.get("text", row.get("line", row.get("lyric", "")))
            if not isinstance(raw_text, str):
                continue

            text = raw_text.strip()
            if not text:
                continue

            cues.append({"time": max(0.0, timestamp), "text": text})

        cues.sort(key=lambda cue: float(cue["time"]))
        return cues

    def load_cues_from_media_url(self, lyrics_url: str) -> tuple[str, list[dict[str, float | str]]]:
        """Load and parse lyrics cues from a /media or /cache URL."""
        lyrics_file = self._media_url_to_file(lyrics_url)
        if lyrics_file is None:
            raise ValueError("Lyrics path must be a /media or /cache URL")
        if not lyrics_file.exists() or not lyrics_file.is_file():
            raise FileNotFoundError(f"Lyrics file not found: {lyrics_file}")

        suffix = lyrics_file.suffix.lower()
        raw_content = lyrics_file.read_text(encoding="utf-8")

        if suffix == ".json":
            return "json", self.parse_json_to_cues(raw_content)
        if suffix == ".lrc":
            return "lrc", self.parse_lrc_to_cues(raw_content)

        raise ValueError(f"Unsupported lyrics format: {suffix}")

    @staticmethod
    def _media_url_to_file(media_url: str | None) -> Path | None:
        """Map a /media or /cache URL back to local filesystem path."""
        if not media_url:
            return None
        if media_url.startswith("/media/"):
            return LyricsService._resolve_safe_sidecar_path(
                settings.media_path, media_url.removeprefix("/media/")
            )
        if media_url.startswith("/cache/"):
            return LyricsService._resolve_safe_sidecar_path(
                settings.cache_path, media_url.removeprefix("/cache/")
            )
        return None

    @staticmethod
    def _resolve_safe_sidecar_path(base_dir: Path, relative_path: str) -> Path:
        """Resolve sidecar path under media/cache roots only."""
        candidate = (base_dir / relative_path).resolve()
        base_resolved = base_dir.resolve()
        if not str(candidate).startswith(str(base_resolved)):
            raise ValueError("Lyrics path points outside configured storage roots")
        return candidate
