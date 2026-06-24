from .common import *


def _write_provider_file(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_load_custom_lyrics_providers_returns_empty_list_for_blank_paths():
    from services.lyrics_provider_loader import load_custom_lyrics_providers

    assert load_custom_lyrics_providers("") == []


def test_load_custom_lyrics_providers_loads_single_file_module(tmp_path):
    from services.lyrics_provider_loader import load_custom_lyrics_providers
    from services.lyrics_types import InferredSong

    provider_file = tmp_path / "hello_provider.py"
    _write_provider_file(
        provider_file,
        """
from services.lyrics_types import InferredSong


class LyricsProvider:
    name = "hello"

    async def fetch(self, inferred_song: InferredSong, **kwargs):
        return "Hello from custom lyrics"
""",
    )

    providers = load_custom_lyrics_providers(str(provider_file))

    assert [provider.name for provider in providers] == ["hello"]
    payload = asyncio.run(providers[0].fetch(InferredSong(title="Song", artist="Artist", source="input")))
    assert payload == "Hello from custom lyrics"


def test_load_custom_lyrics_providers_scans_directory(tmp_path):
    from services.lyrics_provider_loader import load_custom_lyrics_providers

    provider_dir = tmp_path / "lyrics"
    provider_dir.mkdir()
    _write_provider_file(
        provider_dir / "a_first.py",
        """
class LyricsProvider:
    name = "first"

    async def fetch(self, inferred_song, **kwargs):
        return "first"
""",
    )
    _write_provider_file(
        provider_dir / "b_second.py",
        """
class LyricsProvider:
    name = "second"

    async def fetch(self, inferred_song, **kwargs):
        return "second"
""",
    )

    providers = load_custom_lyrics_providers(str(provider_dir))

    assert [provider.name for provider in providers] == ["first", "second"]


def test_load_custom_lyrics_providers_skips_invalid_modules(tmp_path):
    from services.lyrics_provider_loader import load_custom_lyrics_providers

    provider_dir = tmp_path / "bad"
    provider_dir.mkdir()
    _write_provider_file(provider_dir / "broken.py", "definitely not python")
    _write_provider_file(
        provider_dir / "missing_fetch.py",
        """
class LyricsProvider:
    name = "missing-fetch"
""",
    )
    _write_provider_file(
        provider_dir / "raising.py",
        """
class LyricsProvider:
    name = "raising"

    def __init__(self):
        raise RuntimeError("boom")

    async def fetch(self, inferred_song, **kwargs):
        return "unused"
""",
    )

    assert load_custom_lyrics_providers(str(provider_dir)) == []
