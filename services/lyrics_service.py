"""Lyrics service orchestration, contracts, and cue parsing."""
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

logger = logging.getLogger(__name__)

_TIMESTAMP_PATTERN = re.compile(r"\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]")
_OFFSET_TAG_PATTERN = re.compile(r"^\[offset:([+-]?\d+)\]\s*$", re.IGNORECASE)


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


class LyricsService:
    """Service for lyrics metadata inference, retrieval, and cue parsing."""

    def __init__(
        self,
        metadata_inferrer: Optional[SongMetadataInferrer] = None,
        providers: Optional[list[LyricsProvider]] = None,
    ):
        if metadata_inferrer is None:
            from services.lyrics_inference import YouTubeTitleInferrer

            self.metadata_inferrer = YouTubeTitleInferrer(
                lastfm_api_key=settings.lastfm_api_key
            )
        else:
            self.metadata_inferrer = metadata_inferrer

        if providers is not None:
            self.providers = providers
            return

        from services.lyrics_providers import LRCLibLyricsProvider, MusixmatchLyricsProvider

        default_providers: list[LyricsProvider] = []
        if settings.musixmatch_token.strip():
            default_providers.append(MusixmatchLyricsProvider())
        default_providers.append(LRCLibLyricsProvider())
        self.providers = default_providers

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
        """Fetch lyrics text for a song."""
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


# Backward-compatible re-exports for existing imports.
from services.lyrics_inference import YouTubeTitleInferrer  # noqa: E402
from services.lyrics_providers import LRCLibLyricsProvider, MusixmatchLyricsProvider  # noqa: E402

__all__ = [
    "InferredSong",
    "LyricsPayload",
    "SongMetadataInferrer",
    "LyricsProvider",
    "YouTubeTitleInferrer",
    "LRCLibLyricsProvider",
    "MusixmatchLyricsProvider",
    "LyricsService",
]
