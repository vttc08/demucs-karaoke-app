"""CLI to validate YouTube title -> (title, artist) inference behavior."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.lyrics_service import LyricsService


def _load_sample_titles() -> list[str]:
    """Load sample titles from research fixtures."""
    from lyrics.karaoke_titles import titles

    return [str(title).strip() for title in titles if str(title).strip()]


async def _infer_batch(
    service: LyricsService,
    titles: Iterable[str],
    artist_hint: str | None = None,
) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for original in titles:
        inferred = await service.infer_song_metadata(title=original, artist=artist_hint)
        rows.append(
            {
                "original": original,
                "inferred_title": inferred.title,
                "inferred_artist": inferred.artist,
                "source": inferred.source,
            }
        )
    return rows


def _print_compact(rows: list[dict[str, str | None]]) -> None:
    for row in rows:
        inferred_title = (row["inferred_title"] or "").strip()
        inferred_artist = (row["inferred_artist"] or "").strip()
        if inferred_title and inferred_artist:
            metadata = f"{inferred_title} - {inferred_artist}"
        elif inferred_title:
            metadata = inferred_title
        elif inferred_artist:
            metadata = inferred_artist
        else:
            metadata = "None"
        print(f"Parsing title: {row['original']}")
        print(f"Metadata: {metadata}")
        print(f"Source: {row['source'] or 'unknown'}\n")


async def _run_interactive(service: LyricsService) -> None:
    print("Interactive mode: enter a YouTube title (empty line to quit).")
    while True:
        raw = input("> ").strip()
        if not raw:
            break
        artist_hint = input("artist hint (optional): ").strip() or None
        rows = await _infer_batch(service, [raw], artist_hint=artist_hint)
        _print_compact(rows)


async def _main_async(args: argparse.Namespace) -> int:
    service = LyricsService()
    user_titles = [title.strip() for title in args.title if title.strip()]
    sample_titles = _load_sample_titles() if args.samples else []

    merged: list[str] = []
    seen = set()
    for title in [*sample_titles, *user_titles]:
        if title in seen:
            continue
        seen.add(title)
        merged.append(title)

    if merged:
        rows = await _infer_batch(service, merged, artist_hint=args.artist)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            _print_compact(rows)

    if args.interactive:
        await _run_interactive(service)

    if not merged and not args.interactive:
        print("No titles to infer. Use --samples, --title, or --interactive.")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate title/artist inference using production lyrics service logic.",
    )
    parser.add_argument(
        "--samples",
        action="store_true",
        help="Run inference against lyrics.karaoke_titles.titles sample inputs.",
    )
    parser.add_argument(
        "--title",
        action="append",
        default=[],
        help="Add a custom title to infer (repeatable).",
    )
    parser.add_argument(
        "--artist",
        default=None,
        help="Optional artist hint applied to non-interactive inputs.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start an interactive prompt for manual title inference tests.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print non-interactive inference output as JSON.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
