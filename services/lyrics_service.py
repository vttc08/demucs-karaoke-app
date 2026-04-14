"""Lyrics metadata inference, provider orchestration, and cue parsing."""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

import httpx

from config import settings

try:
    from lyrics.metadata_parser import regex_tidy
except ImportError:
    regex_tidy = None

logger = logging.getLogger(__name__)

_TIMESTAMP_PATTERN = re.compile(r"\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]")
_OFFSET_TAG_PATTERN = re.compile(r"^\[offset:([+-]?\d+)\]\s*$", re.IGNORECASE)
_ARTIST_TITLE_SPLIT = re.compile(r"\s+(?:-|–|—|\|)\s+", re.UNICODE)


@dataclass(frozen=True)
class InferredSong:
    """Best-effort normalized metadata used for lyrics lookup."""

    title: str
    artist: Optional[str]
    source: str


@dataclass(frozen=True)
class LyricsPayload:
    """Lyrics text plus source metadata."""

    lyrics: str
    is_synced: bool
    provider: str
    inferred_song: InferredSong


class SongMetadataInferrer(Protocol):
    """Infers normalized title/artist from noisy YouTube metadata."""

    async def infer(self, title: str, artist: Optional[str] = None) -> InferredSong:
        """Return normalized title/artist inference."""


class LyricsProvider(Protocol):
    """Provider contract for fetching lyrics."""

    name: str

    async def fetch(self, inferred_song: InferredSong) -> Optional[LyricsPayload]:
        """Fetch lyrics for inferred metadata."""


class YouTubeTitleInferrer:
    """Infer artist/title from noisy YouTube-style titles."""

    def __init__(self, lastfm_api_key: str | None = None):
        self.lastfm_api_key = (lastfm_api_key or "").strip()

    async def infer(self, title: str, artist: Optional[str] = None) -> InferredSong:
        base_title = title.strip()
        if not base_title:
            return InferredSong(title="", artist=artist, source="input")

        cleaned_title = self._clean_title(base_title)
        split_title, split_artist = self._split_artist_title(cleaned_title)
        if split_title:
            return InferredSong(
                title=split_title,
                artist=split_artist or self._normalize_artist(artist),
                source="regex",
            )

        if self.lastfm_api_key:
            lastfm_match = await self._lookup_lastfm(cleaned_title)
            if lastfm_match is not None:
                return lastfm_match

        return InferredSong(
            title=self._normalize_title(cleaned_title),
            artist=self._normalize_artist(artist),
            source="input",
        )

    @staticmethod
    def _clean_title(raw_title: str) -> str:
        if regex_tidy is None:
            return " ".join(raw_title.split()).strip()
        cleaned = regex_tidy(raw_title)
        return " ".join(cleaned.split()).strip()

    @staticmethod
    def _normalize_title(raw_title: str) -> str:
        return " ".join(raw_title.split()).strip()

    @staticmethod
    def _normalize_artist(raw_artist: Optional[str]) -> Optional[str]:
        if raw_artist is None:
            return None
        value = " ".join(raw_artist.split()).strip()
        return value or None

    @staticmethod
    def _split_artist_title(raw_title: str) -> tuple[str, Optional[str]]:
        pieces = [piece.strip() for piece in _ARTIST_TITLE_SPLIT.split(raw_title) if piece.strip()]
        if len(pieces) >= 2:
            return pieces[1], pieces[0]
        return raw_title.strip(), None

    async def _lookup_lastfm(self, query: str) -> Optional[InferredSong]:
        params = {
            "method": "track.search",
            "track": query,
            "api_key": self.lastfm_api_key,
            "format": "json",
            "limit": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://ws.audioscrobbler.com/2.0/", params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("LastFM lookup failed query=%r error=%s", query, exc)
            return None

        tracks = (
            payload.get("results", {})
            .get("trackmatches", {})
            .get("track", [])
        )
        if isinstance(tracks, dict):
            tracks = [tracks]
        if not isinstance(tracks, list) or not tracks:
            return None

        best = tracks[0]
        track_name = str(best.get("name", "")).strip()
        artist_name = str(best.get("artist", "")).strip()
        if not track_name:
            return None
        return InferredSong(
            title=self._normalize_title(track_name),
            artist=self._normalize_artist(artist_name),
            source="lastfm",
        )


class LRCLibLyricsProvider:
    """LRCLib-backed lyrics fetch provider."""

    name = "lrclib"

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.lrclib_api_url).rstrip("/")

    async def fetch(self, inferred_song: InferredSong) -> Optional[LyricsPayload]:
        queries = self._build_queries(inferred_song)
        best_entry: dict | None = None
        best_score: int | None = None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for query in queries:
                    response = await client.get(
                        f"{self.base_url}/api/search",
                        params={"q": query},
                    )
                    response.raise_for_status()
                    rows = response.json()
                    if not isinstance(rows, list):
                        continue

                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        score = self._score_entry(row, inferred_song)
                        if best_score is None or score > best_score:
                            best_score = score
                            best_entry = row
        except httpx.HTTPError as exc:
            logger.warning(
                "LRCLib request failed title=%r artist=%r error=%s",
                inferred_song.title,
                inferred_song.artist,
                exc,
            )
            return None

        if not best_entry:
            return None

        synced = best_entry.get("syncedLyrics")
        if isinstance(synced, str) and synced.strip():
            return LyricsPayload(
                lyrics=synced,
                is_synced=True,
                provider=self.name,
                inferred_song=inferred_song,
            )

        plain = best_entry.get("plainLyrics")
        if isinstance(plain, str) and plain.strip():
            return LyricsPayload(
                lyrics=plain,
                is_synced=False,
                provider=self.name,
                inferred_song=inferred_song,
            )

        return None

    @staticmethod
    def _build_queries(inferred_song: InferredSong) -> list[str]:
        queries = [inferred_song.title]
        if inferred_song.artist:
            queries.insert(0, f"{inferred_song.title} {inferred_song.artist}")
            queries.append(f"{inferred_song.artist} - {inferred_song.title}")
        return [query for query in queries if query.strip()]

    @staticmethod
    def _score_entry(entry: dict, inferred_song: InferredSong) -> int:
        normalized_title = inferred_song.title.lower().strip()
        normalized_artist = (inferred_song.artist or "").lower().strip()
        entry_title = str(entry.get("trackName", "")).lower().strip()
        entry_artist = str(entry.get("artistName", "")).lower().strip()

        score = 0
        if normalized_title and entry_title == normalized_title:
            score += 100
        elif normalized_title and normalized_title in entry_title:
            score += 60
        if normalized_artist and entry_artist == normalized_artist:
            score += 40
        elif normalized_artist and normalized_artist in entry_artist:
            score += 20
        if isinstance(entry.get("syncedLyrics"), str) and entry["syncedLyrics"].strip():
            score += 10
        if isinstance(entry.get("plainLyrics"), str) and entry["plainLyrics"].strip():
            score += 2
        return score


class LyricsService:
    """Service for lyrics metadata inference, retrieval, and cue parsing."""

    def __init__(
        self,
        metadata_inferrer: Optional[SongMetadataInferrer] = None,
        providers: Optional[list[LyricsProvider]] = None,
    ):
        self.metadata_inferrer = metadata_inferrer or YouTubeTitleInferrer(
            lastfm_api_key=settings.lastfm_api_key
        )
        self.providers = providers or [LRCLibLyricsProvider()]

    async def infer_song_metadata(self, title: str, artist: Optional[str] = None) -> InferredSong:
        """Infer normalized metadata for downstream lyrics providers."""
        return await self.metadata_inferrer.infer(title=title, artist=artist)

    async def resolve_lyrics(
        self,
        title: str,
        artist: Optional[str] = None,
        youtube_title: Optional[str] = None,
    ) -> Optional[LyricsPayload]:
        """Resolve lyrics payload with provider fallback behavior."""
        lookup_title = (youtube_title or title).strip()
        inferred_song = await self.infer_song_metadata(title=lookup_title, artist=artist)
        if not inferred_song.title:
            return None

        for provider in self.providers:
            payload = await provider.fetch(inferred_song)
            if payload:
                logger.info(
                    "Lyrics resolved provider=%s source=%s title=%r artist=%r synced=%s",
                    payload.provider,
                    inferred_song.source,
                    inferred_song.title,
                    inferred_song.artist,
                    payload.is_synced,
                )
                return payload

        logger.info(
            "Lyrics not found title=%r artist=%r inferred_source=%s",
            inferred_song.title,
            inferred_song.artist,
            inferred_song.source,
        )
        return None

    async def fetch_lyrics(
        self,
        title: str,
        artist: Optional[str] = None,
        youtube_title: Optional[str] = None,
    ) -> Optional[str]:
        """
        Fetch lyrics text for a song.

        Args:
            title: Song title
            artist: Artist name (optional)
            youtube_title: Raw YouTube title to infer metadata from (optional)

        Returns:
            Lyrics text or None if not found
        """
        payload = await self.resolve_lyrics(title=title, artist=artist, youtube_title=youtube_title)
        return payload.lyrics if payload else None

    def parse_lyrics_to_lines(self, lyrics: str) -> list[str]:
        """Parse lyrics text into individual lines."""
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
            raise ValueError('JSON lyrics payload must be a list or {"cues": [...]} object')

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
