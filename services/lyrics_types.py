"""Shared lyrics lookup contracts and payload types."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, TypeAlias

import httpx

from config import settings


@dataclass(frozen=True)
class InferredSong:
    """Best-effort normalized metadata used for lyrics lookup."""

    title: str
    artist: Optional[str]
    source: str


@dataclass(frozen=True)
class LyricsAlternative:
    """Optional representation of the same lookup result in another format."""

    lyrics: str
    format: str
    provider: str
    is_synced: bool


@dataclass(frozen=True)
class LyricsPayload:
    """Lyrics text plus source metadata."""

    lyrics: str
    is_synced: bool
    provider: str
    inferred_song: InferredSong
    provider_score: float | None = None
    provider_details: dict[str, Any] | None = None
    alternatives: tuple[LyricsAlternative, ...] = ()


LyricsResult: TypeAlias = LyricsPayload | str | None


class SongMetadataInferrer(Protocol):
    """Infers normalized title/artist from noisy YouTube metadata."""

    async def infer(self, title: str, artist: Optional[str] = None) -> InferredSong:
        """Return normalized title/artist inference."""


class LyricsProvider(Protocol):
    """Provider contract for fetching lyrics."""

    name: str

    async def fetch(
        self,
        inferred_song: InferredSong,
        **kwargs: Any,
    ) -> LyricsResult:
        """Fetch lyrics for inferred metadata."""


def build_httpx_client_kwargs(timeout: float) -> dict[str, Any]:
    """Build common HTTP client kwargs for outbound lyrics provider requests."""
    kwargs: dict[str, Any] = {"timeout": timeout}
    proxy_url = settings.ytdlp_proxy_url.strip()
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return kwargs
