"""CLI for stepwise lyrics debugging on mobile terminals."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.lyrics_service import LyricsService

from scripts.lyrics_inference_cli import _load_sample_titles

PREVIEW_LINE_LIMIT = 4


def _format_artist_title(title: str, artist: str | None) -> str:
    if artist:
        return f"{title} - {artist}"
    return title


def _preview_lines(lyrics: str, is_synced: bool, limit: int = PREVIEW_LINE_LIMIT) -> list[str]:
    if is_synced:
        lines = [line.rstrip() for line in lyrics.splitlines() if line.strip()]
    else:
        lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
    return lines[:limit]


async def _debug_title(
    service: LyricsService,
    raw_title: str,
    *,
    artist_hint: str | None = None,
    printer: Callable[[str], None] = print,
) -> None:
    printer("")
    printer(f"Input title: {raw_title}")
    if artist_hint:
        printer(f"Artist hint: {artist_hint}")

    inferred = await service.infer_song_metadata(title=raw_title, artist=artist_hint)
    printer(f"Inferred metadata: {_format_artist_title(inferred.title, inferred.artist)}")
    printer(f"Inference source: {inferred.source}")
    printer(f"Provider query title: {inferred.title}")
    printer(f"Provider query artist: {inferred.artist or '(none)'}")

    try:
        payload = await service.resolve_lyrics(
            title=raw_title,
            artist=artist_hint,
            youtube_title=raw_title,
        )
    except Exception as exc:  # pragma: no cover - user-facing debug output
        printer(f"Lyrics fetch error: {exc.__class__.__name__}: {exc}")
        return

    if payload is None:
        printer("Provider: none")
        printer("Lyrics: not found")
        return

    printer(f"Provider: {payload.provider} ({'synced' if payload.is_synced else 'plain'})")
    printer(f"Resolved metadata: {_format_artist_title(payload.inferred_song.title, payload.inferred_song.artist)}")
    printer("Lyrics preview:")
    for line in _preview_lines(payload.lyrics, payload.is_synced):
        printer(f"  {line}")


async def _run_menu(
    service: LyricsService,
    sample_titles: list[str],
    *,
    input_fn: Callable[[str], str] = input,
    printer: Callable[[str], None] = print,
) -> None:
    while True:
        printer("")
        printer("Lyrics debug menu")
        for index, title in enumerate(sample_titles, start=1):
            printer(f"{index:>2}. {title}")
        printer(" m. enter a new YouTube title")
        printer(" q. quit")

        choice = input_fn("Select a number, m, or q: ").strip()
        if not choice:
            continue
        lowered = choice.lower()
        if lowered in {"q", "quit", "exit"}:
            printer("Exiting.")
            return
        if lowered == "m":
            raw_title = input_fn("YouTube title: ").strip()
            if not raw_title:
                printer("No title entered.")
                continue
            artist_hint = input_fn("Artist hint (optional): ").strip() or None
            await _debug_title(service, raw_title, artist_hint=artist_hint, printer=printer)
            continue
        if choice.isdigit():
            index = int(choice) - 1
            if not 0 <= index < len(sample_titles):
                printer("Invalid sample number.")
                continue
            await _debug_title(service, sample_titles[index], printer=printer)
            continue

        printer("Invalid choice. Enter a number, m, or q.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Step through karaoke sample titles and debug lyrics provider lookups.",
    )
    return parser


async def _main_async() -> int:
    service = LyricsService()
    sample_titles = _load_sample_titles()
    if not sample_titles:
        print("No sample titles available.")
        return 1

    await _run_menu(service, sample_titles)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build_parser().parse_args()
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
