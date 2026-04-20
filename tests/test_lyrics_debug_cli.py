"""Tests for the lyrics debug CLI."""
from __future__ import annotations

import pytest

from scripts import lyrics_debug_cli as cli


def test_preview_lines_limits_synced_and_plain_output():
    """Preview helper should trim lyrics to a short debug-friendly excerpt."""
    synced = cli._preview_lines("[00:01.00]Line 1\n[00:02.00]Line 2\n[00:03.00]Line 3", True, limit=2)
    plain = cli._preview_lines("Line 1\n\nLine 2\nLine 3", False, limit=2)

    assert synced == ["[00:01.00]Line 1", "[00:02.00]Line 2"]
    assert plain == ["Line 1", "Line 2"]


def test_format_provider_details_for_netease_debug():
    """Provider details helper should surface NetEase diagnostics when present."""
    details = cli._format_provider_details(
        {
            "song_id": 12345,
            "song_title": "Song A",
            "song_artist": "Artist A",
            "selected_query": "Song A Artist A",
            "selected_score": 123.4,
            "candidate_count": 5,
            "queries_tried": ["Song A Artist A", "Song A"],
        }
    )
    assert details[0] == "song id: 12345"
    assert "selected query: Song A Artist A" in details
    assert "selected score: 123.4" in details
    assert "candidate count: 5" in details
    assert "queries tried:" in details
    assert "  - Song A Artist A" in details


@pytest.mark.asyncio
async def test_debug_title_prints_inference_provider_and_preview():
    """Debug output should show inferred metadata, provider, and lyric preview."""
    from services import lyrics_service as ls_module

    inferred = ls_module.InferredSong(title="Clean Title", artist="Clean Artist", source="lastfm")
    payload = ls_module.LyricsPayload(
        lyrics="[00:01.00]Line 1\n[00:02.00]Line 2\n[00:03.00]Line 3",
        is_synced=True,
        provider="musixmatch",
        inferred_song=inferred,
        provider_score=91.5,
        provider_details={
            "song_id": 777,
            "song_title": "Debug Song",
            "song_artist": "Debug Artist",
            "selected_query": "Debug Song Debug Artist",
            "selected_score": 99.9,
            "queries_tried": ["Debug Song Debug Artist"],
        },
    )

    class FakeService:
        async def infer_song_metadata(self, title: str, artist: str | None = None):
            return inferred

        async def resolve_lyrics(self, title: str, artist: str | None = None, youtube_title: str | None = None):
            return payload

    lines: list[str] = []
    await cli._debug_title(FakeService(), "Raw Title", artist_hint="Artist Hint", printer=lines.append)

    joined = "\n".join(lines)
    assert "Input title: Raw Title" in joined
    assert "Artist hint: Artist Hint" in joined
    assert "Inferred metadata: Clean Title - Clean Artist" in joined
    assert "Provider query title: Clean Title" in joined
    assert "Provider query artist: Clean Artist" in joined
    assert "Provider: musixmatch (synced)" in joined
    assert "Provider score: 91.5" in joined
    assert "song id: 777" in joined
    assert "song title: Debug Song" in joined
    assert "song artist: Debug Artist" in joined
    assert "selected query: Debug Song Debug Artist" in joined
    assert "Lyrics preview:" in joined
    assert "  [00:01.00]Line 1" in joined


@pytest.mark.asyncio
async def test_menu_accepts_sample_and_manual_choices():
    """Menu should let the user pick a bundled title or enter a new one."""
    from services import lyrics_service as ls_module

    sample_titles = ["Sample One", "Sample Two"]
    calls: list[tuple[str, str | None, str | None]] = []

    class FakeService:
        async def infer_song_metadata(self, title: str, artist: str | None = None):
            calls.append(("infer", title, artist))
            return ls_module.InferredSong(title=f"clean:{title}", artist=artist, source="regex")

        async def resolve_lyrics(self, title: str, artist: str | None = None, youtube_title: str | None = None):
            calls.append(("resolve", title, artist))
            return ls_module.LyricsPayload(
                lyrics="[00:01.00]Line 1\n[00:02.00]Line 2",
                is_synced=True,
                provider="lrclib",
                inferred_song=ls_module.InferredSong(title=f"clean:{title}", artist=artist, source="regex"),
            )

    inputs = iter(["1", "m", "Manual Title", "", "q"])
    lines: list[str] = []

    def fake_input(_: str) -> str:
        return next(inputs)

    await cli._run_menu(FakeService(), sample_titles, input_fn=fake_input, printer=lines.append)

    output = "\n".join(lines)
    assert "Lyrics debug menu" in output
    assert "Input title: Sample One" in output
    assert "Input title: Manual Title" in output
    assert "Provider: lrclib (synced)" in output
    assert calls[0] == ("infer", "Sample One", None)
    assert calls[2] == ("infer", "Manual Title", None)
