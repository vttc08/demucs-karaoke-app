"""Lyrics provider implementations."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from config import settings
from services import lyrics_service as ls_module

logger = logging.getLogger(__name__)

_MUSIXMATCH_BASE_URL = "https://apic-desktop.musixmatch.com/ws/1.1/macro.subtitles.get"
_MUSIXMATCH_PARAMS = {
    "format": "json",
    "namespace": "lyrics_richsynched",
    "subtitle_format": "mxm",
    "app_id": "web-desktop-app-v1.0",
}
_MUSIXMATCH_DISCLAIMER_RE = re.compile(r"not\s+for\s+commercial\s+use", re.IGNORECASE)


class LRCLibLyricsProvider:
    """LRCLib-backed lyrics fetch provider."""

    name = "lrclib"

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.lrclib_api_url).rstrip("/")

    async def fetch(self, inferred_song: ls_module.InferredSong) -> Optional[ls_module.LyricsPayload]:
        queries = self._build_queries(inferred_song)
        best_entry: dict | None = None
        best_score: int | None = None

        try:
            async with ls_module.httpx.AsyncClient(timeout=10.0) as client:
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
        except ls_module.httpx.HTTPError as exc:
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
            return ls_module.LyricsPayload(
                lyrics=synced,
                is_synced=True,
                provider=self.name,
                inferred_song=inferred_song,
            )

        plain = best_entry.get("plainLyrics")
        if isinstance(plain, str) and plain.strip():
            return ls_module.LyricsPayload(
                lyrics=plain,
                is_synced=False,
                provider=self.name,
                inferred_song=inferred_song,
            )

        return None

    @staticmethod
    def _build_queries(inferred_song: ls_module.InferredSong) -> list[str]:
        queries = [inferred_song.title]
        if inferred_song.artist:
            queries.insert(0, f"{inferred_song.title} {inferred_song.artist}")
            queries.append(f"{inferred_song.artist} - {inferred_song.title}")
        return [query for query in queries if query.strip()]

    @staticmethod
    def _score_entry(entry: dict, inferred_song: ls_module.InferredSong) -> int:
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


class MusixmatchLyricsProvider:
    """Musixmatch-backed lyrics fetch provider."""

    name = "musixmatch"

    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None):
        self.token = (token if token is not None else settings.musixmatch_token).strip()
        self.base_url = (base_url or _MUSIXMATCH_BASE_URL).rstrip("/")
        self.headers = {
            "authority": "apic-desktop.musixmatch.com",
            "cookie": "x-mxm-token-guid=",
        }

    async def fetch(self, inferred_song: ls_module.InferredSong) -> Optional[ls_module.LyricsPayload]:
        if not self.token or not inferred_song.title.strip():
            return None

        params = {
            **_MUSIXMATCH_PARAMS,
            "q_track": inferred_song.title,
            "q_artist": inferred_song.artist or "",
            "q_artists": inferred_song.artist or "",
            "usertoken": self.token,
        }
        try:
            async with ls_module.httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params, headers=self.headers)
                response.raise_for_status()
                payload = response.json()
        except ls_module.httpx.HTTPError as exc:
            logger.warning(
                "Musixmatch request failed title=%r artist=%r error=%s",
                inferred_song.title,
                inferred_song.artist,
                exc,
            )
            return None
        except ValueError as exc:
            logger.warning(
                "Musixmatch response decode failed title=%r artist=%r error=%s",
                inferred_song.title,
                inferred_song.artist,
                exc,
            )
            return None

        macro_calls = self._extract_macro_calls(payload)
        if macro_calls is None:
            return None

        resolved_song = self._resolve_song(inferred_song, macro_calls)
        synced = self._extract_synced_lrc(macro_calls)
        if synced:
            return ls_module.LyricsPayload(
                lyrics=synced,
                is_synced=True,
                provider=self.name,
                inferred_song=resolved_song,
            )

        plain = self._extract_plain_lyrics(macro_calls)
        if plain:
            return ls_module.LyricsPayload(
                lyrics=plain,
                is_synced=False,
                provider=self.name,
                inferred_song=resolved_song,
            )

        if self._is_instrumental(macro_calls):
            return ls_module.LyricsPayload(
                lyrics="[00:00.00]♪ Instrumental ♪",
                is_synced=True,
                provider=self.name,
                inferred_song=resolved_song,
            )
        return None

    @staticmethod
    def _extract_macro_calls(payload: object) -> Optional[dict]:
        if not isinstance(payload, dict):
            return None

        message = payload.get("message")
        if not isinstance(message, dict):
            return None

        header = message.get("header")
        if isinstance(header, dict):
            status_code = header.get("status_code")
            hint = str(header.get("hint", "")).lower()
            if status_code != 200 and hint == "renew":
                logger.warning("Musixmatch token rejected: renew required")
                return None

        body = message.get("body")
        if not isinstance(body, dict):
            return None

        macro_calls = body.get("macro_calls")
        if not isinstance(macro_calls, dict):
            return None

        matcher_header = (
            macro_calls.get("matcher.track.get", {})
            .get("message", {})
            .get("header", {})
        )
        if not isinstance(matcher_header, dict):
            return None

        matcher_status = matcher_header.get("status_code")
        if matcher_status != 200:
            if matcher_status == 404:
                logger.info("Musixmatch song not found")
            elif matcher_status == 401:
                logger.warning("Musixmatch token timed out or unauthorized")
            else:
                logger.warning("Musixmatch matcher error status=%s", matcher_status)
            return None
        return macro_calls

    @staticmethod
    def _resolve_song(inferred_song: ls_module.InferredSong, macro_calls: dict) -> ls_module.InferredSong:
        track = (
            macro_calls.get("matcher.track.get", {})
            .get("message", {})
            .get("body", {})
            .get("track", {})
        )
        if not isinstance(track, dict):
            return inferred_song

        track_name = str(track.get("track_name", "")).strip() or inferred_song.title
        artist_name = str(track.get("artist_name", "")).strip() or inferred_song.artist
        return ls_module.InferredSong(title=track_name, artist=artist_name, source=inferred_song.source)

    @staticmethod
    def _extract_synced_lrc(macro_calls: dict) -> Optional[str]:
        subtitle_body = (
            macro_calls.get("track.subtitles.get", {})
            .get("message", {})
            .get("body", {})
        )
        if not isinstance(subtitle_body, dict):
            return None

        subtitle_list = subtitle_body.get("subtitle_list")
        if not isinstance(subtitle_list, list) or not subtitle_list:
            return None

        subtitle = subtitle_list[0]
        if not isinstance(subtitle, dict):
            return None

        subtitle_data = subtitle.get("subtitle")
        if not isinstance(subtitle_data, dict):
            return None

        subtitle_payload = subtitle_data.get("subtitle_body")
        if not isinstance(subtitle_payload, str) or not subtitle_payload.strip():
            return None

        try:
            rows = json.loads(subtitle_payload)
        except ValueError:
            logger.warning("Musixmatch subtitle payload is not valid JSON")
            return None
        if not isinstance(rows, list):
            return None

        lines: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            time_obj = row.get("time")
            if not isinstance(time_obj, dict):
                continue

            minutes = MusixmatchLyricsProvider._coerce_int(time_obj.get("minutes"), default=-1)
            seconds = MusixmatchLyricsProvider._coerce_int(time_obj.get("seconds"), default=-1)
            hundredths = MusixmatchLyricsProvider._coerce_int(
                time_obj.get("hundredths"), default=0
            )
            if minutes < 0 or not 0 <= seconds < 60:
                continue
            hundredths = max(0, min(99, hundredths))

            text = str(row.get("text") or "♪").strip()
            lines.append(f"[{minutes:02d}:{seconds:02d}.{hundredths:02d}]{text}")

        if not lines:
            return None
        return "\n".join(lines)

    @staticmethod
    def _extract_plain_lyrics(macro_calls: dict) -> Optional[str]:
        lyrics_body = (
            macro_calls.get("track.lyrics.get", {})
            .get("message", {})
            .get("body", {})
        )
        if not isinstance(lyrics_body, dict):
            return None

        lyrics_data = lyrics_body.get("lyrics")
        if not isinstance(lyrics_data, dict):
            return None
        if bool(lyrics_data.get("restricted")):
            logger.info("Musixmatch lyrics are restricted")
            return None

        plain = lyrics_data.get("lyrics_body")
        if not isinstance(plain, str) or not plain.strip():
            return None

        cleaned_lines = []
        for line in plain.splitlines():
            stripped = line.strip()
            if not stripped:
                cleaned_lines.append("")
                continue
            if _MUSIXMATCH_DISCLAIMER_RE.search(stripped):
                continue
            if set(stripped) == {"*"}:
                continue
            cleaned_lines.append(stripped)
        cleaned = "\n".join(cleaned_lines).strip()
        return cleaned or None

    @staticmethod
    def _is_instrumental(macro_calls: dict) -> bool:
        track = (
            macro_calls.get("matcher.track.get", {})
            .get("message", {})
            .get("body", {})
            .get("track", {})
        )
        if not isinstance(track, dict):
            return False
        return bool(track.get("instrumental"))

    @staticmethod
    def _coerce_int(value: object, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
