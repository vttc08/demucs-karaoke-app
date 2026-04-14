"""Tests for lyrics inference CLI helper."""
import argparse

import pytest

from scripts import lyrics_inference_cli as cli


@pytest.mark.asyncio
async def test_infer_batch_uses_service_inference():
    """Batch helper should call the same inference path as production service."""

    class FakeService:
        async def infer_song_metadata(self, title: str, artist: str | None = None):
            return type(
                "Inferred",
                (),
                {"title": f"{title}-clean", "artist": artist or "X", "source": "fake"},
            )()

    rows = await cli._infer_batch(FakeService(), ["A", "B"], artist_hint="Hint")
    assert rows == [
        {
            "original": "A",
            "inferred_title": "A-clean",
            "inferred_artist": "Hint",
            "source": "fake",
        },
        {
            "original": "B",
            "inferred_title": "B-clean",
            "inferred_artist": "Hint",
            "source": "fake",
        },
    ]


def test_cli_parser_accepts_repeatable_title_and_samples():
    """Parser should accept mixed sample + custom title inputs."""
    parser = cli.build_parser()
    args = parser.parse_args(["--samples", "--title", "Song A", "--title", "Song B"])
    assert isinstance(args, argparse.Namespace)
    assert args.samples is True
    assert args.title == ["Song A", "Song B"]


def test_print_compact_mobile_friendly_output(capsys):
    """Compact formatter should print one title block at a time."""
    cli._print_compact(
        [
            {
                "original": "Taylor Swift - Enchanted (Lyric Video)",
                "inferred_title": "Enchanted",
                "inferred_artist": "Taylor Swift",
                "source": "lastfm",
            }
        ]
    )

    output = capsys.readouterr().out
    assert "Parsing title: Taylor Swift - Enchanted (Lyric Video)" in output
    assert "Metadata: Enchanted - Taylor Swift" in output
    assert "Source: lastfm" in output
