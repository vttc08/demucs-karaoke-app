"""Lyrics provider implementations."""
from __future__ import annotations

import base64
import asyncio
import difflib
import json
import logging
import random
import re
import string
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

try:
    from Crypto.Cipher import AES as _AES
except ImportError:  # pragma: no cover - optional dependency
    _AES = None

from config import settings
from services import lyrics_types as ls_module
from services.ttml_parser import TTMLParseError, is_valid_xml, parse_ttml_to_whisperx_segments

logger = logging.getLogger(__name__)

_MUSIXMATCH_BASE_URL = "https://apic-desktop.musixmatch.com/ws/1.1/macro.subtitles.get"
_MUSIXMATCH_PARAMS = {
    "format": "json",
    "namespace": "lyrics_richsynched",
    "subtitle_format": "mxm",
    "app_id": "web-desktop-app-v1.0",
}
_MUSIXMATCH_DISCLAIMER_RE = re.compile(r"not\s+for\s+commercial\s+use", re.IGNORECASE)
_NETEASE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_NETEASE_NONCE = "0CoJUm6Qyw8W8jud"
_NETEASE_IV = "0102030405060708"
_NETEASE_PUBKEY = "010001"
_NETEASE_MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725"
    "152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312"
    "ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424"
    "d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
)
_NETEASE_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]")
_NETEASE_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_NETEASE_MAX_QUERIES = 6
_NETEASE_EARLY_STOP_SCORE = 120.0
_ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$", re.IGNORECASE)


@dataclass(frozen=True)
class _NeteaseSongCandidate:
    song_id: int
    title: str
    artists: list[str]
    album: str
    duration_ms: int


class LRCLibLyricsProvider:
    """LRCLib-backed lyrics fetch provider."""

    name = "lrclib"

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.lrclib_api_url).rstrip("/")

    async def fetch(self, inferred_song: ls_module.InferredSong, **kwargs: Any) -> Optional[ls_module.LyricsPayload]:
        queries = self._build_queries(inferred_song)
        best_entry: dict | None = None
        best_score: float | None = None

        try:
            async with ls_module.httpx.AsyncClient(
                **ls_module.build_httpx_client_kwargs(timeout=10.0)
            ) as client:
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
                provider_score=best_score,
            )

        plain = best_entry.get("plainLyrics")
        if isinstance(plain, str) and plain.strip():
            return ls_module.LyricsPayload(
                lyrics=plain,
                is_synced=False,
                provider=self.name,
                inferred_song=inferred_song,
                provider_score=best_score,
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

    async def fetch(self, inferred_song: ls_module.InferredSong, **kwargs: Any) -> Optional[ls_module.LyricsPayload]:
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
            async with ls_module.httpx.AsyncClient(
                **ls_module.build_httpx_client_kwargs(timeout=10.0)
            ) as client:
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
            alternatives: tuple[ls_module.LyricsAlternative, ...] = ()
            isrc = self._extract_isrc(macro_calls)
            if isrc:
                ttml = await self._fetch_ttml(isrc)
                if ttml:
                    alternatives = (
                        ls_module.LyricsAlternative(
                            lyrics=ttml,
                            format="ttml",
                            provider="lyrics-storage",
                            is_synced=True,
                        ),
                    )
            return ls_module.LyricsPayload(
                lyrics=synced,
                is_synced=True,
                provider=self.name,
                inferred_song=resolved_song,
                provider_score=120.0,
                alternatives=alternatives,
            )

        plain = self._extract_plain_lyrics(macro_calls)
        if plain:
            return ls_module.LyricsPayload(
                lyrics=plain,
                is_synced=False,
                provider=self.name,
                inferred_song=resolved_song,
                provider_score=90.0,
            )

        if self._is_instrumental(macro_calls):
            return ls_module.LyricsPayload(
                lyrics="[00:00.00]♪ Instrumental ♪",
                is_synced=True,
                provider=self.name,
                inferred_song=resolved_song,
                provider_score=70.0,
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
        subtitle_body = MusixmatchLyricsProvider._extract_macro_body(
            macro_calls, "track.subtitles.get", "tracks.subtitles.get"
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
    def _extract_macro_body(macro_calls: dict, *names: str) -> dict:
        for name in names:
            call = macro_calls.get(name)
            if not isinstance(call, dict):
                continue
            message = call.get("message")
            body = message.get("body") if isinstance(message, dict) else None
            if isinstance(body, dict):
                return body
        return {}

    @staticmethod
    def _extract_isrc(macro_calls: dict) -> Optional[str]:
        """Extract the first usable ISRC from the matcher macro response."""
        body = MusixmatchLyricsProvider._extract_macro_body(macro_calls, "matcher.track.get")
        track = body.get("track")
        if not isinstance(track, dict):
            return None

        candidates: list[object] = []
        commontrack_isrcs = track.get("commontrack_isrcs")
        if isinstance(commontrack_isrcs, list):
            candidates.extend(commontrack_isrcs)
        candidates.append(track.get("track_isrc"))

        def flatten(values: list[object]):
            for value in values:
                if isinstance(value, list):
                    yield from flatten(value)
                else:
                    yield value

        for candidate in flatten(candidates):
            normalized = str(candidate or "").strip().upper()
            if _ISRC_RE.fullmatch(normalized):
                return normalized
        return None

    async def _fetch_ttml(self, isrc: str) -> Optional[str]:
        base_url = settings.lyrics_ttml_storage_url.strip().rstrip("/")
        if not base_url:
            return None

        try:
            timeout_seconds = max(0.1, float(settings.lyrics_ttml_upgrade_timeout_seconds))
        except (TypeError, ValueError):
            timeout_seconds = 3.0

        url = f"{base_url}/{isrc}.ttml"
        timeout = ls_module.httpx.Timeout(
            timeout_seconds,
            connect=min(timeout_seconds, 1.5),
            read=timeout_seconds,
            write=min(timeout_seconds, 1.5),
            pool=min(timeout_seconds, 1.5),
        )
        client_kwargs = ls_module.build_httpx_client_kwargs(timeout_seconds)
        client_kwargs["timeout"] = timeout
        try:
            async with asyncio.timeout(timeout_seconds):
                async with ls_module.httpx.AsyncClient(**client_kwargs) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    content = response.text.strip()
        except (asyncio.TimeoutError, ls_module.httpx.HTTPError) as exc:
            logger.info("TTML upgrade unavailable isrc=%s error=%s", isrc, exc)
            return None

        if not is_valid_xml(content):
            logger.info("TTML upgrade returned invalid XML isrc=%s", isrc)
            return None
        try:
            if not parse_ttml_to_whisperx_segments(content):
                logger.info("TTML upgrade returned no timed cues isrc=%s", isrc)
                return None
        except TTMLParseError as exc:
            logger.info("TTML upgrade parse failed isrc=%s error=%s", isrc, exc)
            return None
        return content

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


class NeteaseLyricsProvider:
    """NetEase-backed lyrics fetch provider.

    Search and lyric request behavior is adapted from:
    - cqjjjzr/MusicBee-NeteaseLyrics (C# plugin logic)
    - Gaohaoyang/netease-music-downloader (TS implementation details)
    """

    name = "netease"
    _warned_missing_crypto = False

    def __init__(self):
        self.search_url = "https://music.163.com/weapi/search/get"
        self.lyric_url = "https://music.163.com/weapi/song/lyric?csrf_token="
        self.legacy_search_url = "http://music.163.com/api/search/get/"
        self.legacy_lyric_url = "http://music.163.com/api/song/lyric"
        self.headers = {
            "Referer": "https://music.163.com",
            "User-Agent": _NETEASE_USER_AGENT,
        }

    async def fetch(self, inferred_song: ls_module.InferredSong, **kwargs: Any) -> Optional[ls_module.LyricsPayload]:
        if not inferred_song.title.strip():
            return None

        candidates, search_debug = await self._search_candidates(inferred_song)
        candidate = self._select_best_candidate(candidates, inferred_song)
        if candidate is None:
            return None

        lyric_payload = await self._request_lyrics(candidate.song_id)
        if lyric_payload is None:
            return None

        lyric_text = self._extract_lyric_text(lyric_payload, "lrc")
        if not lyric_text:
            return None

        translated_text = self._extract_lyric_text(lyric_payload, "tlyric")
        is_synced = self._looks_synced(lyric_text)
        if is_synced and translated_text:
            lyric_text = self._merge_translated_lyrics(lyric_text, translated_text)

        resolved_song = ls_module.InferredSong(
            title=candidate.title or inferred_song.title,
            artist=", ".join(candidate.artists) if candidate.artists else inferred_song.artist,
            source=inferred_song.source,
        )
        return ls_module.LyricsPayload(
            lyrics=lyric_text,
            is_synced=is_synced,
            provider=self.name,
            inferred_song=resolved_song,
            provider_score=float(search_debug.get("selected_score") or 0.0),
            provider_details={
                "song_id": candidate.song_id,
                "song_title": candidate.title,
                "song_artist": ", ".join(candidate.artists),
                "selected_query": search_debug.get("selected_query"),
                "selected_score": search_debug.get("selected_score"),
                "queries_tried": search_debug.get("queries_tried"),
                "candidate_count": search_debug.get("candidate_count"),
            },
        )

    async def _search_candidates(
        self, inferred_song: ls_module.InferredSong
    ) -> tuple[list[_NeteaseSongCandidate], dict[str, Any]]:
        candidates_by_id: dict[int, _NeteaseSongCandidate] = {}
        search_debug: dict[str, Any] = {"queries_tried": [], "candidate_count": 0, "selected_query": None, "selected_score": None}
        for query in self._build_queries(inferred_song)[:_NETEASE_MAX_QUERIES]:
            rows = await self._request_search(query)
            search_debug["queries_tried"].append(query)
            for row in rows:
                candidates_by_id[row.song_id] = row
            if not rows:
                continue
            scored_rows = [(self._score_candidate(row, inferred_song), row) for row in rows]
            scored_rows.sort(key=lambda item: item[0])
            best_score, _ = scored_rows[-1]
            if (
                search_debug["selected_score"] is None
                or best_score > float(search_debug["selected_score"])
            ):
                search_debug["selected_query"] = query
                search_debug["selected_score"] = best_score
            if best_score >= _NETEASE_EARLY_STOP_SCORE:
                break
        search_debug["candidate_count"] = len(candidates_by_id)
        return list(candidates_by_id.values()), search_debug

    async def _request_search(self, query: str) -> list[_NeteaseSongCandidate]:
        payload = {
            "csrf_token": "",
            "s": query,
            "offset": 0,
            "type": 1,
            "limit": 20,
        }
        try:
            return await self._request_search_weapi(payload)
        except (RuntimeError, ls_module.httpx.HTTPError, ValueError) as exc:
            logger.info("NetEase weapi search failed query=%r error=%s; trying legacy API", query, exc)
        return await self._request_search_legacy(query)

    async def _request_search_weapi(self, payload: dict[str, Any]) -> list[_NeteaseSongCandidate]:
        encrypted = self._weapi_encrypt(payload)
        async with ls_module.httpx.AsyncClient(
            **ls_module.build_httpx_client_kwargs(timeout=10.0)
        ) as client:
            response = await client.post(
                self.search_url,
                data=encrypted,
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
        return self._parse_search_response(data)

    async def _request_search_legacy(self, query: str) -> list[_NeteaseSongCandidate]:
        params = {
            "csrf_token": "",
            "hlpretag": "",
            "hlposttag": "",
            "s": query,
            "type": 1,
            "offset": 0,
            "total": "true",
            "limit": 6,
        }
        try:
            async with ls_module.httpx.AsyncClient(
                **ls_module.build_httpx_client_kwargs(timeout=10.0)
            ) as client:
                response = await client.get(
                    self.legacy_search_url,
                    params=params,
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()
        except (ls_module.httpx.HTTPError, ValueError) as exc:
            logger.warning("NetEase legacy search failed query=%r error=%s", query, exc)
            return []
        return self._parse_search_response(data)

    async def _request_lyrics(self, song_id: int) -> Optional[dict[str, Any]]:
        payload = {
            "os": "pc",
            "id": song_id,
            "lv": -1,
            "kv": -1,
            "tv": -1,
            "rv": -1,
        }
        try:
            data = await self._request_lyrics_weapi(payload)
            if int(data.get("code", 0)) == 200:
                return data
        except (RuntimeError, ls_module.httpx.HTTPError, ValueError) as exc:
            logger.info("NetEase weapi lyric request failed song_id=%s error=%s; trying legacy API", song_id, exc)
        return await self._request_lyrics_legacy(song_id)

    async def _request_lyrics_weapi(self, payload: dict[str, Any]) -> dict[str, Any]:
        encrypted = self._weapi_encrypt(payload)
        async with ls_module.httpx.AsyncClient(
            **ls_module.build_httpx_client_kwargs(timeout=10.0)
        ) as client:
            response = await client.post(
                self.lyric_url,
                data=encrypted,
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("NetEase lyric payload was not a JSON object")
        return data

    async def _request_lyrics_legacy(self, song_id: int) -> Optional[dict[str, Any]]:
        params = {"os": "pc", "id": song_id, "lv": -1, "kv": -1, "tv": -1}
        headers = {**self.headers, "Cookie": "appver=1.5.0.75771;"}
        try:
            async with ls_module.httpx.AsyncClient(
                **ls_module.build_httpx_client_kwargs(timeout=10.0)
            ) as client:
                response = await client.get(
                    self.legacy_lyric_url,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except (ls_module.httpx.HTTPError, ValueError) as exc:
            logger.warning("NetEase legacy lyric request failed song_id=%s error=%s", song_id, exc)
            return None

        if not isinstance(data, dict):
            return None
        if int(data.get("code", 0)) != 200:
            return None
        return data

    @staticmethod
    def _parse_search_response(payload: object) -> list[_NeteaseSongCandidate]:
        if not isinstance(payload, dict):
            return []
        if int(payload.get("code", 0)) != 200:
            return []

        songs = (payload.get("result") or {}).get("songs") if isinstance(payload.get("result"), dict) else None
        if not isinstance(songs, list):
            return []

        out: list[_NeteaseSongCandidate] = []
        for row in songs:
            if not isinstance(row, dict):
                continue
            song_id = row.get("id")
            try:
                normalized_song_id = int(song_id)
            except (TypeError, ValueError):
                continue
            artists = [
                str(artist.get("name") or "").strip()
                for artist in (row.get("artists") or [])
                if isinstance(artist, dict)
            ]
            album = row.get("album")
            album_name = str(album.get("name") or "").strip() if isinstance(album, dict) else ""
            out.append(
                _NeteaseSongCandidate(
                    song_id=normalized_song_id,
                    title=str(row.get("name") or "").strip(),
                    artists=[artist for artist in artists if artist],
                    album=album_name,
                    duration_ms=int(row.get("duration") or 0),
                )
            )
        return out

    @staticmethod
    def _build_queries(inferred_song: ls_module.InferredSong) -> list[str]:
        title_variants = NeteaseLyricsProvider._title_variants(inferred_song.title)
        artist_variants = NeteaseLyricsProvider._artist_variants(inferred_song.artist or "")
        queries = [inferred_song.title]
        if inferred_song.artist:
            queries.insert(0, f"{inferred_song.title} {inferred_song.artist}")
            queries.append(f"{inferred_song.artist} - {inferred_song.title}")
        for title in title_variants:
            queries.append(title)
            for artist in artist_variants:
                queries.append(f"{title} {artist}")
                queries.append(f"{artist} - {title}")
        return NeteaseLyricsProvider._unique_non_empty(queries)

    @staticmethod
    def _select_best_candidate(
        candidates: list[_NeteaseSongCandidate], inferred_song: ls_module.InferredSong
    ) -> Optional[_NeteaseSongCandidate]:
        if not candidates:
            return None
        scored = [
            (NeteaseLyricsProvider._score_candidate(candidate, inferred_song), candidate.song_id, candidate)
            for candidate in candidates
        ]
        scored.sort()
        best_score, _, best_candidate = scored[-1]
        if best_score < 60:
            logger.info(
                "NetEase candidate rejected: low confidence score=%s title=%r artist=%r",
                f"{best_score:.1f}",
                inferred_song.title,
                inferred_song.artist,
            )
            return None
        return best_candidate

    @staticmethod
    def _score_candidate(candidate: _NeteaseSongCandidate, inferred_song: ls_module.InferredSong) -> float:
        title_variants = NeteaseLyricsProvider._title_variants(inferred_song.title)
        artist_variants = NeteaseLyricsProvider._artist_variants(inferred_song.artist or "")
        candidate_title = NeteaseLyricsProvider._normalize_text(candidate.title)
        candidate_title_cjk = NeteaseLyricsProvider._extract_cjk(candidate.title)
        candidate_artist = NeteaseLyricsProvider._normalize_text(", ".join(candidate.artists))
        candidate_artist_cjk = NeteaseLyricsProvider._extract_cjk(", ".join(candidate.artists))

        title_similarity = max(
            (
                NeteaseLyricsProvider._similarity(
                    NeteaseLyricsProvider._normalize_text(variant), candidate_title
                )
                for variant in title_variants
            ),
            default=0.0,
        )
        title_cjk_similarity = max(
            (
                NeteaseLyricsProvider._similarity(
                    NeteaseLyricsProvider._extract_cjk(variant), candidate_title_cjk
                )
                for variant in title_variants
                if NeteaseLyricsProvider._extract_cjk(variant)
            ),
            default=0.0,
        )
        best_title_similarity = max(title_similarity, title_cjk_similarity)
        if best_title_similarity < 0.42:
            return 0.0

        artist_similarity = max(
            (
                NeteaseLyricsProvider._similarity(
                    NeteaseLyricsProvider._normalize_text(variant), candidate_artist
                )
                for variant in artist_variants
            ),
            default=0.0,
        )
        artist_cjk_similarity = max(
            (
                NeteaseLyricsProvider._similarity(
                    NeteaseLyricsProvider._extract_cjk(variant), candidate_artist_cjk
                )
                for variant in artist_variants
                if NeteaseLyricsProvider._extract_cjk(variant)
            ),
            default=0.0,
        )
        best_artist_similarity = max(artist_similarity, artist_cjk_similarity)

        score = (best_title_similarity * 100.0) + (title_cjk_similarity * 30.0) + (
            best_artist_similarity * 70.0
        )
        if candidate_title and any(
            NeteaseLyricsProvider._normalize_text(variant) == candidate_title
            for variant in title_variants
        ):
            score += 25.0
        if candidate_artist and any(
            NeteaseLyricsProvider._normalize_text(variant) == candidate_artist
            for variant in artist_variants
        ):
            score += 15.0
        if artist_variants:
            if best_artist_similarity < 0.2:
                score -= 50.0
            elif best_artist_similarity < 0.35:
                score -= 20.0
        return score

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()
        return re.sub(r"[^\w\s\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", "", normalized)

    @staticmethod
    def _extract_cjk(value: str) -> str:
        return "".join(_NETEASE_CJK_RE.findall(unicodedata.normalize("NFKC", value)))

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return difflib.SequenceMatcher(None, left, right).ratio()

    @staticmethod
    def _title_variants(title: str) -> list[str]:
        normalized = NeteaseLyricsProvider._normalize_whitespace(title)
        variants = [normalized]

        title_without_parentheses = re.sub(r"\([^)]*\)", " ", normalized).strip()
        if title_without_parentheses:
            variants.append(title_without_parentheses)

        title_cjk = NeteaseLyricsProvider._extract_cjk(normalized)
        if title_cjk:
            variants.append(title_cjk)

        title_no_latin = re.sub(r"[A-Za-z]+", " ", normalized).strip()
        title_no_latin = NeteaseLyricsProvider._normalize_whitespace(title_no_latin)
        if title_no_latin:
            variants.append(title_no_latin)

        return NeteaseLyricsProvider._unique_non_empty(variants)

    @staticmethod
    def _artist_variants(artist: str) -> list[str]:
        normalized = NeteaseLyricsProvider._normalize_whitespace(artist)
        variants = [normalized]

        artist_cjk = NeteaseLyricsProvider._extract_cjk(normalized)
        if artist_cjk:
            variants.append(artist_cjk)

        artist_no_latin = re.sub(r"[A-Za-z]+", " ", normalized).strip()
        artist_no_latin = NeteaseLyricsProvider._normalize_whitespace(artist_no_latin)
        if artist_no_latin:
            variants.append(artist_no_latin)

        return NeteaseLyricsProvider._unique_non_empty(variants)

    @staticmethod
    def _normalize_whitespace(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _unique_non_empty(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)
        return result

    @staticmethod
    def _extract_lyric_text(payload: dict[str, Any], key: str) -> Optional[str]:
        item = payload.get(key)
        if not isinstance(item, dict):
            return None
        text = item.get("lyric")
        if not isinstance(text, str):
            return None
        stripped = text.strip()
        return stripped or None

    @staticmethod
    def _looks_synced(lyrics: str) -> bool:
        return any(_NETEASE_TIMESTAMP_RE.search(line) for line in lyrics.splitlines())

    @staticmethod
    def _merge_translated_lyrics(original_lrc: str, translated_lrc: str) -> str:
        translations = NeteaseLyricsProvider._timestamp_to_text_map(translated_lrc)
        if not translations:
            return original_lrc

        merged_lines: list[str] = []
        for line in original_lrc.splitlines():
            matches = list(_NETEASE_TIMESTAMP_RE.finditer(line))
            if not matches:
                merged_lines.append(line)
                continue

            base_text = _NETEASE_TIMESTAMP_RE.sub("", line).strip()
            if not base_text:
                merged_lines.append(line)
                continue

            translation = None
            for match in matches:
                timestamp_key = NeteaseLyricsProvider._timestamp_key(match)
                if timestamp_key in translations:
                    translation = translations[timestamp_key]
                    break
            if translation and translation not in base_text:
                merged_lines.append("".join(match.group(0) for match in matches) + f"{base_text}/{translation}")
            else:
                merged_lines.append(line)
        return "\n".join(merged_lines).strip()

    @staticmethod
    def _timestamp_to_text_map(lyrics: str) -> dict[int, str]:
        out: dict[int, str] = {}
        for line in lyrics.splitlines():
            matches = list(_NETEASE_TIMESTAMP_RE.finditer(line))
            if not matches:
                continue
            text = _NETEASE_TIMESTAMP_RE.sub("", line).strip()
            if not text:
                continue
            for match in matches:
                out[NeteaseLyricsProvider._timestamp_key(match)] = text
        return out

    @staticmethod
    def _timestamp_key(match: re.Match[str]) -> int:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        fraction_raw = match.group(3) or "0"
        millis = int(fraction_raw.ljust(3, "0")[:3])
        return (minutes * 60 + seconds) * 1000 + millis

    @staticmethod
    def _weapi_encrypt(payload: dict[str, Any]) -> dict[str, str]:
        if _AES is None:
            if not NeteaseLyricsProvider._warned_missing_crypto:
                logger.info("pycryptodome not installed; NetEase provider will use legacy API fallback")
                NeteaseLyricsProvider._warned_missing_crypto = True
            raise RuntimeError("AES-CBC encryption support unavailable")

        text = json.dumps(payload, separators=(",", ":"))
        secret_key = NeteaseLyricsProvider._random_secret_key()
        params = NeteaseLyricsProvider._aes_cbc_base64(
            NeteaseLyricsProvider._aes_cbc_base64(text, _NETEASE_NONCE),
            secret_key,
        )
        enc_sec_key = NeteaseLyricsProvider._rsa_enc_sec_key(secret_key)
        return {"params": params, "encSecKey": enc_sec_key}

    @staticmethod
    def _aes_cbc_base64(plaintext: str, key: str) -> str:
        assert _AES is not None
        cipher = _AES.new(key.encode("utf-8"), _AES.MODE_CBC, _NETEASE_IV.encode("utf-8"))
        padded = NeteaseLyricsProvider._pkcs7_pad(plaintext.encode("utf-8"))
        encrypted = cipher.encrypt(padded)
        return base64.b64encode(encrypted).decode("utf-8")

    @staticmethod
    def _pkcs7_pad(data: bytes) -> bytes:
        pad_len = 16 - (len(data) % 16)
        return data + bytes([pad_len]) * pad_len

    @staticmethod
    def _rsa_enc_sec_key(secret_key: str) -> str:
        reversed_key = secret_key[::-1]
        key_int = int(reversed_key.encode("utf-8").hex(), 16)
        pubkey_int = int(_NETEASE_PUBKEY, 16)
        modulus_int = int(_NETEASE_MODULUS, 16)
        encrypted = pow(key_int, pubkey_int, modulus_int)
        return format(encrypted, "x").zfill(256)

    @staticmethod
    def _random_secret_key(length: int = 16) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(random.choice(alphabet) for _ in range(length))
