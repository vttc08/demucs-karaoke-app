"""Docker yt-dlp configuration regression tests."""

from config import Settings


def test_settings_preserve_explicit_ytdlp_path():
    assert Settings(ytdlp_path="/data/tools/yt-dlp").ytdlp_path == "/data/tools/yt-dlp"
