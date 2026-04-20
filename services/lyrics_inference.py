"""Lyrics metadata inference utilities."""
from __future__ import annotations

import logging
import re
from typing import Optional

from services import lyrics_service as ls_module

logger = logging.getLogger(__name__)

_ARTIST_TITLE_SPLIT = re.compile(r"\s+(?:-|–|—|\|)\s+", re.UNICODE)
_SEPARATOR_NORMALIZE_RE = re.compile(r"\s*[-–—|]+\s*")
_TITLE_NOISE_PATTERNS = [
    re.compile(r"\s*\((?:official|lyric[s]?|karaoke|mv|video|audio|hd|4k|8k)[^)]*\)\s*$", re.IGNORECASE),
    re.compile(r"\s*\[(?:official|lyric[s]?|karaoke|mv|video|audio|hd|4k|8k)[^\]]*\]\s*$", re.IGNORECASE),
    re.compile(r"\s*(?:official|lyric[s]?|karaoke|mv|video|audio|hd|4k|8k)\s*$", re.IGNORECASE),
]
_LASTFM_QUERY_NOISE = re.compile(
    r"\b(?:official|lyrics?|karaoke|video|audio|full\s+video|live|hd|4k|8k|version|theme)\b",
    re.IGNORECASE,
)


class YouTubeTitleInferrer:
    """Infer artist/title from noisy YouTube-style titles."""

    def __init__(self, lastfm_api_key: str | None = None):
        self.lastfm_api_key = (lastfm_api_key or "").strip()

    async def infer(self, title: str, artist: Optional[str] = None) -> ls_module.InferredSong:
        base_title = title.strip()
        if not base_title:
            return ls_module.InferredSong(title="", artist=artist, source="input")

        cleaned_title = self._clean_title(base_title)
        split_title, split_artist = self._split_artist_title(cleaned_title)
        normalized_artist = self._normalize_artist(artist)

        if self.lastfm_api_key:
            lastfm_query = self._build_lastfm_query(
                cleaned_title=cleaned_title,
                split_title=split_title,
                split_artist=split_artist,
                artist_hint=normalized_artist,
            )
            lastfm_match = await self._lookup_lastfm(lastfm_query)
            if lastfm_match is not None:
                return lastfm_match

        if split_title:
            return ls_module.InferredSong(
                title=split_title,
                artist=split_artist or normalized_artist,
                source="regex",
            )

        if normalized_artist:
            return ls_module.InferredSong(
                title=self._normalize_title(cleaned_title),
                artist=normalized_artist,
                source="input",
            )

        return ls_module.InferredSong(
            title=self._normalize_title(cleaned_title),
            artist=normalized_artist,
            source="input",
        )

    @staticmethod
    def _clean_title(raw_title: str) -> str:
        cleaned = raw_title.replace("_", " ").strip()
        cleaned = _SEPARATOR_NORMALIZE_RE.sub(" - ", cleaned)
        cleaned = " ".join(cleaned.split())
        for pattern in _TITLE_NOISE_PATTERNS:
            previous = None
            while previous != cleaned:
                previous = cleaned
                cleaned = pattern.sub("", cleaned).strip()
        return cleaned

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
        if len(pieces) < 2:
            return "", None

        left = pieces[0]
        right = pieces[1]
        left_as_artist = left, right
        right_as_artist = right, left

        left_score = (
            YouTubeTitleInferrer._score_artist_candidate(left_as_artist[0])
            + YouTubeTitleInferrer._score_title_candidate(left_as_artist[1])
        )
        right_score = (
            YouTubeTitleInferrer._score_artist_candidate(right_as_artist[0])
            + YouTubeTitleInferrer._score_title_candidate(right_as_artist[1])
        )

        if right_score > left_score:
            return right_as_artist[1], right_as_artist[0]
        return left_as_artist[1], left_as_artist[0]

    @staticmethod
    def _score_title_candidate(segment: str) -> int:
        lower = segment.lower()
        score = 0
        words = [word for word in segment.split() if word]
        if words:
            score += 1
        if len(words) <= 5:
            score += 2
        if len(words) <= 3:
            score += 1
        if any(token in lower for token in ("karaoke", "lyric", "lyrics", "official", "video", "mv", "live", "theme")):
            score += 1
        if re.search(r"[\(\)\[\]!?']", segment):
            score += 1
        if any(char.isdigit() for char in segment):
            score += 1
        if YouTubeTitleInferrer._looks_like_artist_name(segment):
            score -= 3
        return score

    @staticmethod
    def _score_artist_candidate(segment: str) -> int:
        lower = segment.lower()
        score = 0
        words = [word for word in segment.split() if word]
        if words:
            score += 1
        if len(words) <= 5:
            score += 2
        if len(words) <= 3:
            score += 1
        if any(token in lower for token in ("feat", "ft", "featuring", "&", ",", " and ")):
            score += 2
        if YouTubeTitleInferrer._looks_like_artist_name(segment):
            score += 3
        if any(token in lower for token in ("karaoke", "lyric", "lyrics", "official", "video", "mv", "live", "theme")):
            score -= 4
        if re.search(r"[\(\)\[\]]", segment):
            score -= 1
        return score

    @staticmethod
    def _looks_like_artist_name(segment: str) -> bool:
        tokens = [token for token in re.split(r"\s+", segment.strip()) if token]
        if not tokens or len(tokens) > 5:
            return False
        latin_tokens = [token for token in tokens if re.search(r"[A-Za-z]", token)]
        if not latin_tokens:
            return False
        return all(token[:1].isupper() or token.isupper() for token in latin_tokens)

    @staticmethod
    def _clean_search_query(song_name: str) -> str:
        cleaned = re.sub(r"\([^)]*\)", " ", song_name)
        cleaned = re.sub(r"\[[^\]]*\]", " ", cleaned)
        cleaned = _LASTFM_QUERY_NOISE.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|")
        return cleaned or song_name

    @staticmethod
    def _split_query_parts(query: str) -> tuple[str, str]:
        parts = re.split(r"\s+[-|]\s+", query.lower())
        if len(parts) < 2:
            parts = re.split(r"\s*[-|]\s*", query.lower())
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
        return query.lower().strip(), ""

    @staticmethod
    def _normalize_for_comparison(text: str) -> str:
        normalized = text.lower().replace("&", " and ")
        normalized = normalized.replace("'", "").replace("\u2019", "")
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @staticmethod
    def _is_similar(a: str, b: str) -> bool:
        return bool(a) and bool(b) and (a == b or a in b or b in a)

    def _detect_artist_first(self, original_query: str, artist: str, title: str) -> bool:
        part1_raw, part2_raw = self._split_query_parts(original_query)
        if not part2_raw:
            return False

        part1 = self._normalize_for_comparison(part1_raw)
        part2 = self._normalize_for_comparison(part2_raw)
        artist_norm = self._normalize_for_comparison(artist)
        title_norm = self._normalize_for_comparison(title)

        part1_is_artist = self._is_similar(part1, artist_norm)
        part1_is_title = self._is_similar(part1, title_norm)
        part2_is_artist = self._is_similar(part2, artist_norm)
        part2_is_title = self._is_similar(part2, title_norm)

        if part1_is_artist and part2_is_title:
            return True
        if part1_is_title and part2_is_artist:
            return False
        if part1_is_artist and not part1_is_title:
            return True
        if part1_is_title and not part1_is_artist:
            return False
        if part2_is_title and not part2_is_artist:
            return True
        if part2_is_artist and not part2_is_title:
            return False
        return False

    @staticmethod
    def _strip_artist_from_track(track_name: str, artist_name: str) -> str:
        track_normalized = YouTubeTitleInferrer._normalize_for_comparison(track_name)
        artist_normalized = YouTubeTitleInferrer._normalize_for_comparison(artist_name)

        if track_normalized.startswith(artist_normalized + " "):
            match = re.match(r"^.{0,50}?(?:\s*[-\u2013\u2014|:]\s*|\s+/\s+)(.+)$", track_name)
            if match:
                before_separator = track_name[: match.start(1)].strip()
                before_separator = re.sub(r"\s*[-\u2013\u2014|:/]\s*$", "", before_separator)
                if YouTubeTitleInferrer._normalize_for_comparison(before_separator) == artist_normalized:
                    return match.group(1)

        return track_name

    @staticmethod
    def _score_lastfm_result(result: dict, original_query: str) -> int:
        track_name = str(result.get("name", "")).strip().lower()
        artist_name = str(result.get("artist", "")).strip().lower()
        if not track_name or not artist_name:
            return -1000

        part1, part2 = YouTubeTitleInferrer._split_query_parts(original_query)
        part1_normalized = YouTubeTitleInferrer._normalize_for_comparison(part1)
        part2_normalized = YouTubeTitleInferrer._normalize_for_comparison(part2)
        track_normalized = YouTubeTitleInferrer._normalize_for_comparison(track_name)
        artist_normalized = YouTubeTitleInferrer._normalize_for_comparison(artist_name)

        score = 0

        if part2_normalized:
            if part1_normalized == track_normalized and part2_normalized == artist_normalized:
                score += 100
            elif part2_normalized == track_normalized and part1_normalized == artist_normalized:
                score += 100
            elif part1_normalized and part1_normalized in track_normalized:
                score += 50
            elif part2_normalized and part2_normalized in track_normalized:
                score += 50
        else:
            if part1_normalized == track_normalized:
                score += 100
            elif part1_normalized in track_normalized:
                score += 50

        if artist_normalized not in part1_normalized and artist_normalized not in part2_normalized:
            score -= 100
        if artist_normalized in track_normalized:
            score -= 50
        if " - " in track_name or any(token in track_name for token in ("live", "version", "remix")):
            score -= 30
        if len(track_name) > 60:
            score -= 20
        if str(result.get("name", "")).isupper() or str(result.get("artist", "")).isupper():
            score -= 10
        if result.get("mbid"):
            score += 5
        return score

    @staticmethod
    def _build_lastfm_query(
        cleaned_title: str,
        split_title: str,
        split_artist: Optional[str],
        artist_hint: Optional[str],
    ) -> str:
        if split_title and (split_artist or artist_hint):
            return f"{split_artist or artist_hint} - {split_title}"
        return cleaned_title

    async def _lookup_lastfm(self, query: str) -> Optional[ls_module.InferredSong]:
        cleaned_query = self._clean_search_query(query)
        params = {
            "method": "track.search",
            "track": cleaned_query,
            "api_key": self.lastfm_api_key,
            "format": "json",
            "limit": 10,
        }
        try:
            async with ls_module.httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://ws.audioscrobbler.com/2.0/", params=params)
                response.raise_for_status()
                payload = response.json()
        except ls_module.httpx.HTTPError as exc:
            logger.warning("LastFM lookup failed query=%r error=%s", query, exc)
            return None

        if not isinstance(payload, dict):
            return None

        tracks = payload.get("results", {}).get("trackmatches", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        if not isinstance(tracks, list) or not tracks:
            return None

        candidates = [row for row in tracks if isinstance(row, dict)]
        if not candidates:
            return None
        best = max(candidates, key=lambda row: self._score_lastfm_result(row, cleaned_query))
        track_name = str(best.get("name", "")).strip()
        artist_name = str(best.get("artist", "")).strip()
        if not track_name:
            return None
        clean_track_name = self._strip_artist_from_track(track_name, artist_name)
        if self._detect_artist_first(cleaned_query, artist_name, clean_track_name):
            return ls_module.InferredSong(
                title=self._normalize_title(clean_track_name),
                artist=self._normalize_artist(artist_name),
                source="lastfm",
            )
        return ls_module.InferredSong(
            title=self._normalize_title(clean_track_name),
            artist=self._normalize_artist(artist_name),
            source="lastfm",
        )
