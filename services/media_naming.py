"""Helpers for human-readable media filenames."""
from __future__ import annotations

import re
from typing import Optional

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_segment(value: str) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", value).strip()
    cleaned = _INVALID_FILENAME_CHARS.sub("-", cleaned)
    cleaned = cleaned.strip(" .-_")
    return cleaned


def build_media_stem(title: str, artist: Optional[str] = None, fallback: Optional[str] = None) -> str:
    """Build a human-readable, filesystem-safe media stem."""
    title_part = _clean_segment(title)
    artist_part = _clean_segment(artist or "")

    if artist_part and title_part:
        stem = f"{artist_part} - {title_part}"
    elif title_part:
        stem = title_part
    elif artist_part:
        stem = artist_part
    else:
        stem = _clean_segment(fallback or "media")

    return stem or _clean_segment(fallback or "media") or "media"
