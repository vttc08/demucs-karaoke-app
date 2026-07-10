"""Lyrics orchestration and cue parsing."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Optional

from config import settings
from services.lyrics_inference import YouTubeTitleInferrer
from services.lyrics_provider_loader import load_custom_lyrics_providers
from services.lyrics_providers import (
    LRCLibLyricsProvider,
    MusixmatchLyricsProvider,
    NeteaseLyricsProvider,
)
from services.lyrics_types import (
    InferredSong,
    LyricsPayload,
    LyricsProvider,
    SongMetadataInferrer,
)
from services.ttml_parser import TTMLParseError, is_valid_xml, parse_ttml_to_whisperx_segments

logger = logging.getLogger(__name__)

_TIMESTAMP_PATTERN = re.compile(r"\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]")
_OFFSET_TAG_PATTERN = re.compile(r"^\[offset:([+-]?\d+)\]\s*$", re.IGNORECASE)
_SYNCED_LYRICS_HINT_RE = re.compile(r"(?m)^\s*\[\d{1,3}:\d{2}(?:\.\d{1,3})?\]")

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
        self._uses_runtime_provider_settings = providers is None
        self._custom_provider_paths: str = ""
        self._custom_providers_cache: list[LyricsProvider] = []
        if providers is not None:
            self.providers = providers
            return

        self.providers = self._build_default_providers()

    @staticmethod
    def _build_default_providers() -> list[LyricsProvider]:
        default_providers: list[LyricsProvider] = []
        if settings.musixmatch_token.strip():
            default_providers.append(MusixmatchLyricsProvider())
        if settings.lyrics_provider_netease_enabled:
            default_providers.append(NeteaseLyricsProvider())
        if settings.lyrics_provider_lrclib_enabled:
            default_providers.append(LRCLibLyricsProvider())
        return default_providers

    def _get_custom_providers(self) -> list[LyricsProvider]:
        custom_paths = settings.lyrics_provider_custom_paths.strip()
        if not custom_paths:
            self._custom_provider_paths = ""
            self._custom_providers_cache = []
            return []

        if custom_paths == self._custom_provider_paths:
            return self._custom_providers_cache

        providers = load_custom_lyrics_providers(custom_paths)
        self._custom_provider_paths = custom_paths
        self._custom_providers_cache = providers
        return providers

    async def infer_song_metadata(self, title: str, artist: Optional[str] = None) -> InferredSong:
        """Infer normalized metadata for downstream lyrics providers."""
        inferred = await self.metadata_inferrer.infer(title=title, artist=artist)
        logger.debug(
            "Inferred lyrics metadata title=%r artist=%r source=%s",
            inferred.title,
            inferred.artist,
            inferred.source,
        )
        return inferred

    async def resolve_lyrics(
        self,
        title: str,
        artist: Optional[str] = None,
        youtube_title: Optional[str] = None,
        infer: Optional[bool] = True,
    ) -> Optional[LyricsPayload]:
        """Resolve lyrics payload with provider fallback behavior."""
        lookup_title = (youtube_title or title).strip()
        logger.debug("Got YouTube title=%r artist=%r", lookup_title, artist)
        if infer:
            inferred_song = await self.infer_song_metadata(title=lookup_title, artist=artist)
        else:
            inferred_song = InferredSong(title=lookup_title, artist=artist, source="input")
        if not inferred_song.title:
            return None
        if self._uses_runtime_provider_settings:
            self.providers = self._build_default_providers()
        debug_query = self._build_debug_query(inferred_song)

        musixmatch_providers = [provider for provider in self.providers if provider.name == "musixmatch"]
        fallback_providers = [provider for provider in self.providers if provider.name != "musixmatch"]

        for provider in musixmatch_providers:
            logger.debug("Searching provider=%s with query=%r", provider.name, debug_query)
            payload = await provider.fetch(
                inferred_song,
                title=inferred_song.title,
                artist=inferred_song.artist,
            )
            if payload:
                logger.debug(
                    "Found lyrics provider=%s synced=%s title=%r artist=%r",
                    payload.provider,
                    payload.is_synced,
                    payload.inferred_song.title,
                    payload.inferred_song.artist,
                )
                logger.info(
                    "Lyrics resolved provider=%s score=%s source=%s title=%r artist=%r synced=%s",
                    payload.provider,
                    self._score_payload(payload),
                    inferred_song.source,
                    inferred_song.title,
                    inferred_song.artist,
                    payload.is_synced,
                    )
                return payload
            logger.debug("Provider %s lyrics not found query=%r", provider.name, debug_query)

        custom_providers = self._get_custom_providers() if self._uses_runtime_provider_settings else []
        fallback_entries = [(provider, False) for provider in fallback_providers]
        fallback_entries.extend((provider, True) for provider in custom_providers)
        if fallback_entries:
            async def _fetch_provider(provider: LyricsProvider, is_custom: bool):
                logger.debug(
                    "Searching provider=%s custom=%s with query=%r",
                    provider.name,
                    is_custom,
                    debug_query,
                )
                try:
                    result = await provider.fetch(
                        inferred_song,
                        title=inferred_song.title,
                        artist=inferred_song.artist,
                    )
                    return provider, is_custom, result
                except Exception as exc:  # pragma: no cover - defensive logging
                    return provider, is_custom, exc

            results = await asyncio.gather(
                *(_fetch_provider(provider, is_custom) for provider, is_custom in fallback_entries)
            )
            payloads: list[tuple[LyricsProvider, bool, LyricsPayload]] = []
            for provider, is_custom, result in results:
                if isinstance(result, Exception):
                    logger.error(
                        "Lyrics provider raised provider=%s custom=%s title=%r artist=%r",
                        provider.name,
                        is_custom,
                        inferred_song.title,
                        inferred_song.artist,
                        exc_info=(type(result), result, result.__traceback__),
                    )
                    continue
                normalized_payload = self._normalize_provider_result(
                    provider=provider,
                    inferred_song=inferred_song,
                    result=result,
                )
                if normalized_payload:
                    payloads.append((provider, is_custom, normalized_payload))
                else:
                    logger.debug(
                        "Provider %s lyrics not found query=%r custom=%s",
                        provider.name,
                        debug_query,
                        is_custom,
                    )

            if payloads:
                _best_provider, best_is_custom, best_payload = max(
                    payloads,
                    key=lambda item: (
                        self._score_payload(item[2]),
                        0 if item[1] else 1,
                    ),
                )
                logger.debug(
                    "Found lyrics provider=%s synced=%s title=%r artist=%r custom=%s",
                    best_payload.provider,
                    best_payload.is_synced,
                    best_payload.inferred_song.title,
                    best_payload.inferred_song.artist,
                    best_is_custom,
                )
                logger.info(
                    "Lyrics resolved provider=%s score=%s source=%s title=%r artist=%r synced=%s custom=%s",
                    best_payload.provider,
                    self._score_payload(best_payload),
                    inferred_song.source,
                    inferred_song.title,
                    inferred_song.artist,
                    best_payload.is_synced,
                    best_is_custom,
                )
                return best_payload

        logger.info(
            "Lyrics not found title=%r artist=%r inferred_source=%s",
            inferred_song.title,
            inferred_song.artist,
            inferred_song.source,
        )
        logger.debug("Provider lookup exhausted lyrics not found query=%r", debug_query)
        return None

    async def fetch_lyrics(
        self,
        title: str,
        artist: Optional[str] = None,
        youtube_title: Optional[str] = None,
        infer: Optional[bool] = True,
    ) -> Optional[str]:
        """
        Fetch lyrics text for a song.

        Args:
            title: Song title
            artist: Artist name (optional)
            youtube_title: Raw YouTube title to infer metadata from (optional)
            infer: Whether to infer song metadata if not provided

        Returns:
            Lyrics text or None if not found
        """
        payload = await self.resolve_lyrics(title=title, artist=artist, youtube_title=youtube_title, infer=infer)
        return payload.lyrics if payload else None

    def parse_lyrics_to_lines(self, lyrics: str) -> list[str]:
        """Parse lyrics text into individual lines."""
        return [line.strip() for line in lyrics.split("\n") if line.strip()]

    @staticmethod
    def _score_payload(payload: LyricsPayload) -> float:
        if payload.provider_score is not None:
            return float(payload.provider_score)
        provider_details = payload.provider_details or {}
        selected_score = provider_details.get("selected_score")
        if isinstance(selected_score, (int, float)):
            return float(selected_score)
        return 0.0

    def _normalize_provider_result(
        self,
        provider: LyricsProvider,
        inferred_song: InferredSong,
        result: object,
    ) -> Optional[LyricsPayload]:
        if isinstance(result, LyricsPayload):
            return result
        if isinstance(result, str):
            lyrics_text = result.strip()
            if not lyrics_text:
                return None
            return LyricsPayload(
                lyrics=lyrics_text,
                is_synced=self._looks_like_synced_lyrics(lyrics_text),
                provider=provider.name,
                inferred_song=inferred_song,
            )
        return None

    @staticmethod
    def _looks_like_synced_lyrics(lyrics_text: str) -> bool:
        return bool(_SYNCED_LYRICS_HINT_RE.search(lyrics_text))

    @staticmethod
    def _build_debug_query(inferred_song: InferredSong) -> str:
        if inferred_song.artist:
            return f"{inferred_song.artist} - {inferred_song.title}"
        return inferred_song.title

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

    def parse_json_to_cues(self, payload: str) -> list[dict[str, object]]:
        """Parse JSON lyrics cues and normalize their shape."""
        data = json.loads(payload)
        rows: Any = None
        if isinstance(data, dict):
            for key in ("cues", "segments", "items", "lines"):
                if key in data:
                    rows = data.get(key)
                    break
        else:
            rows = data
        if not isinstance(rows, list):
            raise ValueError('JSON lyrics payload must be a list or {"cues": [...]} object')

        cues: list[dict[str, object]] = []
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
            if not isinstance(raw_text, str) or not raw_text.strip():
                words = row.get("words")
                if isinstance(words, list):
                    raw_text = " ".join(
                        str(word.get("word", "")).strip()
                        for word in words
                        if isinstance(word, dict) and str(word.get("word", "")).strip()
                    )
                if not isinstance(raw_text, str) or not raw_text.strip():
                    continue

            text = raw_text.strip()
            if not text:
                continue

            cue: dict[str, object] = {"time": max(0.0, timestamp), "text": text}
            raw_end = row.get("end")
            if isinstance(raw_end, (int, float)):
                end = float(raw_end)
                if math.isfinite(end) and end >= timestamp:
                    cue["end"] = max(0.0, end)
            raw_words = row.get("words")
            if isinstance(raw_words, list):
                words: list[dict[str, object]] = []
                words_are_complete = bool(raw_words)
                for raw_word in raw_words:
                    if not isinstance(raw_word, dict):
                        words_are_complete = False
                        continue

                    word_text = str(raw_word.get("word", "")).strip()
                    raw_start = raw_word.get("start")
                    raw_end = raw_word.get("end")
                    if (
                        not word_text
                        or not isinstance(raw_start, (int, float))
                        or not isinstance(raw_end, (int, float))
                    ):
                        words_are_complete = False
                        continue

                    start = float(raw_start)
                    end = float(raw_end)
                    if not math.isfinite(start) or not math.isfinite(end) or end < start:
                        words_are_complete = False
                        continue

                    words.append({
                        "word": word_text,
                        "start": max(0.0, start),
                        "end": max(0.0, end),
                    })

                if words_are_complete and words:
                    words.sort(key=lambda word: float(word["start"]))
                    cue["words"] = words

            cues.append(cue)

        cues.sort(key=lambda cue: float(cue["time"]))
        return cues

    @staticmethod
    def parse_text_to_lines(payload: str) -> list[str]:
        """Parse plain text lyrics into non-empty display lines."""
        return [line.strip() for line in payload.splitlines() if line.strip()]

    def load_lyrics_payload_from_media_url(self, lyrics_url: str) -> dict[str, object]:
        """Load normalized lyrics payload from a /media or /cache URL."""
        lyrics_file = self._media_url_to_file(lyrics_url)
        if lyrics_file is None:
            raise ValueError("Lyrics path must be a /media or /cache URL")
        if not lyrics_file.exists() or not lyrics_file.is_file():
            raise FileNotFoundError(f"Lyrics file not found: {lyrics_file}")

        suffix = lyrics_file.suffix.lower()
        raw_content = lyrics_file.read_text(encoding="utf-8")

        if suffix == ".json":
            cues = self.parse_json_to_cues(raw_content)
            return {
                "source_format": "json",
                "is_synced": True,
                "cues": cues,
                "lines": [str(cue["text"]) for cue in cues],
            }
        if suffix == ".lrc":
            cues = self.parse_lrc_to_cues(raw_content)
            return {
                "source_format": "lrc",
                "is_synced": True,
                "cues": cues,
                "lines": [str(cue["text"]) for cue in cues],
            }
        if suffix == ".txt":
            lines = self.parse_text_to_lines(raw_content)
            return {
                "source_format": "txt",
                "is_synced": False,
                "cues": [],
                "lines": lines,
            }
        if suffix == ".ttml":
            if not is_valid_xml(raw_content):
                raise ValueError("TTML lyrics must be valid XML")
            try:
                segments = parse_ttml_to_whisperx_segments(raw_content)
            except TTMLParseError as exc:
                raise ValueError(str(exc)) from exc
            cues = [
                {
                    "time": float(segment["start"]),
                    "end": float(segment["end"]),
                    "text": str(segment["text"]),
                    "words": list(segment.get("words") or []),
                }
                for segment in segments
            ]
            return {
                "source_format": "ttml",
                "is_synced": True,
                "cues": cues,
                "lines": [str(cue["text"]) for cue in cues],
            }

        raise ValueError(f"Unsupported lyrics format: {suffix}")

    def load_cues_from_media_url(self, lyrics_url: str) -> tuple[str, list[dict[str, object]]]:
        """Load and parse lyrics cues from a /media or /cache URL."""
        payload = self.load_lyrics_payload_from_media_url(lyrics_url)
        if not payload.get("is_synced"):
            raise ValueError(
                f"Unsupported lyrics format for timed cues: {payload.get('source_format')}"
            )
        return str(payload["source_format"]), list(payload["cues"])

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


__all__ = [
    "InferredSong",
    "LyricsPayload",
    "SongMetadataInferrer",
    "LyricsProvider",
    "YouTubeTitleInferrer",
    "LRCLibLyricsProvider",
    "MusixmatchLyricsProvider",
    "NeteaseLyricsProvider",
    "LyricsService",
]
