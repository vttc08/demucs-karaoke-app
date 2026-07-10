"""Pytest configuration."""
import sys
from pathlib import Path

import pytest

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def fast_websocket_heartbeat():
    """Keep WebSocket integration tests from waiting on the production heartbeat interval."""
    from config import settings

    original_interval = settings.ws_heartbeat_interval
    original_ytdlp_video_codec = settings.ytdlp_video_codec
    original_ffmpeg_audio_codec = settings.ffmpeg_audio_codec
    original_separation_backend = settings.separation_backend
    original_sherpa_spleeter_model = settings.sherpa_spleeter_model
    settings.ws_heartbeat_interval = 1
    settings.ytdlp_video_codec = ""
    settings.ffmpeg_audio_codec = ""
    try:
        yield
    finally:
        settings.ws_heartbeat_interval = original_interval
        settings.ytdlp_video_codec = original_ytdlp_video_codec
        settings.ffmpeg_audio_codec = original_ffmpeg_audio_codec
        settings.separation_backend = original_separation_backend
        settings.sherpa_spleeter_model = original_sherpa_spleeter_model
