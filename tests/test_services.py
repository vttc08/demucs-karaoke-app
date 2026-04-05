"""Tests for service layer."""
import pytest
import httpx
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path
from services.queue_service import QueueService
from services.youtube_service import YouTubeService
from services.karaoke_service import KaraokeService
from services.lyrics_service import LyricsService
from services.demucs_client import DemucsClient
from services.runtime_settings_service import RuntimeSettingsService
from services.websocket_manager import ConnectionManager
from config import EXPLICIT_SETTINGS_FIELDS, settings
from models import (
    Base,
    DemucsHealthResponse,
    QueueItem,
    QueueItemCreate,
    RuntimeSetting,
    QueueStatus,
    RuntimeSettingsUpdateRequest,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_services.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_queue_service_add_to_queue(db_session):
    """Test adding item to queue via service."""
    service = QueueService()
    item = QueueItemCreate(
        youtube_id="test123",
        title="Test Song",
        artist="Test Artist",
        is_karaoke=True,
        burn_lyrics=True,
    )

    result = service.add_to_queue(db_session, item)

    assert result.youtube_id == "test123"
    assert result.title == "Test Song"
    assert result.burn_lyrics is True
    assert result.status == QueueStatus.PENDING


def test_queue_service_get_queue(db_session):
    """Test getting queue via service."""
    service = QueueService()

    # Add items
    item1 = QueueItemCreate(
        youtube_id="test1", title="Song 1", is_karaoke=False, burn_lyrics=True
    )
    item2 = QueueItemCreate(
        youtube_id="test2", title="Song 2", is_karaoke=True, burn_lyrics=True
    )
    service.add_to_queue(db_session, item1)
    service.add_to_queue(db_session, item2)

    # Get queue
    queue = service.get_queue(db_session)

    assert len(queue) == 2
    assert queue[0].title == "Song 1"
    assert queue[0].burn_lyrics is False
    assert queue[1].title == "Song 2"
    assert queue[1].burn_lyrics is True


def test_queue_service_update_status(db_session):
    """Test updating item status."""
    service = QueueService()
    item = QueueItemCreate(
        youtube_id="test123", title="Test Song", is_karaoke=False, burn_lyrics=True
    )
    result = service.add_to_queue(db_session, item)

    # Update status
    service.update_status(db_session, result.id, QueueStatus.READY)

    # Verify
    updated_queue = service.get_queue(db_session)
    assert updated_queue[0].status == QueueStatus.READY


@pytest.mark.asyncio
async def test_queue_service_update_status_async_broadcasts(db_session):
    """Async status updates should broadcast queue_item_updated events."""
    service = QueueService()
    item = QueueItemCreate(
        youtube_id="async-status", title="Async Status", is_karaoke=False
    )
    created = service.add_to_queue(db_session, item)

    manager = ConnectionManager()

    class DummySocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    socket = DummySocket()
    manager.active_connections.append(socket)

    with patch("services.websocket_manager.manager", manager):
        await service.update_status_async(db_session, created.id, QueueStatus.READY)

    assert len(socket.messages) == 1
    assert socket.messages[0]["type"] == "queue_item_updated"
    assert socket.messages[0]["data"]["id"] == created.id
    assert socket.messages[0]["data"]["status"] == "ready"


def test_queue_service_skip_current_item_promotes_next_ready(db_session):
    """Test skipping current item promotes next ready item."""
    service = QueueService()
    current = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="play1", title="Current", is_karaoke=False),
    )
    next_item = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="play2", title="Next", is_karaoke=True),
    )

    service.update_status(db_session, current.id, QueueStatus.PLAYING)
    service.update_status(db_session, next_item.id, QueueStatus.READY)

    promoted = service.skip_current_item(db_session)
    assert promoted is not None
    assert promoted.id == next_item.id
    assert promoted.status == QueueStatus.PLAYING

    current_after = (
        db_session.query(QueueItem).filter(QueueItem.id == current.id).first()
    )
    assert current_after is None


def test_queue_service_skip_current_item_without_next_returns_none(db_session):
    """Test skipping current item with no next ready item."""
    service = QueueService()
    current = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="play3", title="Only Song", is_karaoke=False),
    )
    service.update_status(db_session, current.id, QueueStatus.PLAYING)

    promoted = service.skip_current_item(db_session)
    assert promoted is None

    current_after = (
        db_session.query(QueueItem).filter(QueueItem.id == current.id).first()
    )
    assert current_after is None


def test_queue_service_complete_current_promotes_next_ready(db_session):
    """Completing current item should promote next ready item."""
    service = QueueService()
    current = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="c1", title="Current", is_karaoke=False),
    )
    next_item = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="n1", title="Next", is_karaoke=False),
    )

    service.update_status(db_session, current.id, QueueStatus.PLAYING)
    service.update_status(db_session, next_item.id, QueueStatus.READY)

    promoted = service.complete_current_item(db_session)
    assert promoted is not None
    assert promoted.id == next_item.id
    assert promoted.status == QueueStatus.PLAYING

    current_after = (
        db_session.query(QueueItem).filter(QueueItem.id == current.id).first()
    )
    assert current_after is None


def test_queue_service_complete_current_without_next_returns_none(db_session):
    """Completing current item with no ready next item should return none."""
    service = QueueService()
    current = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="only1", title="Only", is_karaoke=False),
    )
    service.update_status(db_session, current.id, QueueStatus.PLAYING)

    promoted = service.complete_current_item(db_session)
    assert promoted is None

    current_after = (
        db_session.query(QueueItem).filter(QueueItem.id == current.id).first()
    )
    assert current_after is None


def test_queue_service_complete_current_promotes_when_none_playing(db_session):
    """If nothing is playing, complete-current still promotes next ready item."""
    service = QueueService()
    next_item = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="r1", title="Ready Next", is_karaoke=False),
    )
    service.update_status(db_session, next_item.id, QueueStatus.READY)

    promoted = service.complete_current_item(db_session)
    assert promoted is not None
    assert promoted.id == next_item.id
    assert promoted.status == QueueStatus.PLAYING


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search(mock_ytdlp):
    """Test YouTube search service."""
    # Mock yt-dlp search results
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "test123",
            "title": "Test Video",
            "channel": "Test Channel",
            "duration": "3:45",
            "thumbnail": "http://example.com/thumb.jpg",
        }
    ]
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("test query")

    assert len(results) == 1
    assert results[0].video_id == "test123"
    assert results[0].title == "Test Video"
    assert results[0].thumbnail == "http://example.com/thumb.jpg"


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_uses_thumbnail_fallback(mock_ytdlp):
    """Search should derive thumbnail URL when missing from yt-dlp output."""
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "abc123",
            "title": "Video Without Thumbnail",
            "channel": "Channel Name",
            "duration": "4:00",
            "thumbnail": None,
        }
    ]
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("test query")

    assert len(results) == 1
    assert results[0].video_id == "abc123"
    assert (
        results[0].thumbnail
        == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    )


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_detects_youtube_url(mock_ytdlp):
    """YouTube URL query should resolve via single-video metadata fetch."""
    mock_instance = Mock()
    mock_instance.get_video_info.return_value = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "channel": "RickAstleyVEVO",
        "duration": "3:33",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    }
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("https://youtu.be/dQw4w9WgXcQ")

    assert len(results) == 1
    assert results[0].video_id == "dQw4w9WgXcQ"
    mock_instance.get_video_info.assert_called_once()
    mock_instance.search.assert_not_called()


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_detects_raw_youtube_id(mock_ytdlp):
    """11-char YouTube IDs should be treated as direct video input."""
    mock_instance = Mock()
    mock_instance.get_video_info.return_value = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Direct ID",
        "channel": "Channel",
        "duration": "1:00",
        "thumbnail": None,
    }
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("dQw4w9WgXcQ")

    assert len(results) == 1
    assert results[0].video_id == "dQw4w9WgXcQ"
    called_url = mock_instance.get_video_info.call_args[0][0]
    assert called_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    mock_instance.search.assert_not_called()


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_download_video_with_audio(mock_ytdlp):
    """Test progressive video+audio download delegation."""
    mock_instance = Mock()
    mock_path = Path("/tmp/karaoke_media/test123.mp4")
    mock_instance.download_video_with_audio.return_value = mock_path
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    result = service.download_video_with_audio("test123")

    assert result == mock_path
    mock_instance.download_video_with_audio.assert_called_once()


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_uses_latest_media_path_setting(mock_ytdlp, tmp_path):
    """YouTube service should honor runtime media_path changes."""
    mock_instance = Mock()
    mock_instance.download_video_with_audio.return_value = tmp_path / "v.mp4"
    mock_ytdlp.return_value = mock_instance

    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media-now"
        service = YouTubeService()
        service.download_video_with_audio("id123")
        called_output_dir = mock_instance.download_video_with_audio.call_args[0][1]
        assert called_output_dir == settings.media_path
    finally:
        settings.media_path = original_media


@pytest.mark.asyncio
async def test_karaoke_service_non_karaoke_uses_progressive_download(db_session):
    """Non-karaoke processing should use video+audio direct download."""
    queue_service = QueueService()
    item = queue_service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="plain123",
            title="Plain Song",
            is_karaoke=False,
            burn_lyrics=False,
        ),
    )

    service = KaraokeService()
    service.youtube_service = Mock()
    service.queue_service = queue_service
    service.youtube_service.download_video_with_audio.return_value = Path(
        "/tmp/karaoke_media/plain123.mp4"
    )

    await service.process_queue_item(db_session, item.id)

    service.youtube_service.download_video_with_audio.assert_called_once_with("plain123")
    service.youtube_service.download_video.assert_not_called()
    service.youtube_service.download_audio.assert_not_called()

    updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
    assert updated_item is not None
    assert updated_item.status == QueueStatus.READY
    assert updated_item.media is not None
    assert updated_item.media.media_path == "/media/plain123.mp4"


@pytest.mark.asyncio
async def test_lyrics_service_fetch():
    """Lyrics service should prefer syncedLyrics from LRCLIB results."""
    service = LyricsService()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "trackName": "Test Song",
                    "artistName": "Test Artist",
                    "syncedLyrics": "[00:01.00]Synced line",
                    "plainLyrics": "Plain line",
                }
            ]

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            assert url.endswith("/api/search")
            assert "Test Song" in params["q"]
            return FakeResponse()

    from services import lyrics_service as ls_module

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        lyrics = await service.fetch_lyrics("Test Song", "Test Artist")
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert lyrics == "[00:01.00]Synced line"


@pytest.mark.asyncio
async def test_lyrics_service_fetch_falls_back_to_plain():
    """Lyrics service should fall back to plain lyrics when synced lyrics is missing."""
    service = LyricsService()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "trackName": "Another Song",
                    "artistName": "Another Artist",
                    "syncedLyrics": None,
                    "plainLyrics": "Plain only line",
                }
            ]

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            return FakeResponse()

    from services import lyrics_service as ls_module

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        lyrics = await service.fetch_lyrics("Another Song", "Another Artist")
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert lyrics == "Plain only line"


@pytest.mark.asyncio
async def test_karaoke_service_karaoke_without_burn_uses_remux(db_session):
    """Karaoke processing without burn_lyrics should remux instead of burning."""
    queue_service = QueueService()
    item = queue_service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="kara123",
            title="Kara Song",
            is_karaoke=True,
            burn_lyrics=False,
        ),
    )

    service = KaraokeService()
    service.queue_service = queue_service
    service.youtube_service = Mock()
    service.lyrics_service = Mock()
    service.demucs_client = Mock()
    service.ffmpeg = Mock()
    service.youtube_service.download_video.return_value = Path("/tmp/video.mp4")
    service.youtube_service.download_audio.return_value = Path("/tmp/audio.wav")
    service.demucs_client.separate_vocals = AsyncMock(return_value=Mock(
        no_vocals_path="/tmp/no_vocals.wav"
    ))

    await service.process_queue_item(db_session, item.id)

    service.ffmpeg.combine_audio_video.assert_called_once()
    service.ffmpeg.burn_subtitles.assert_not_called()


@pytest.mark.asyncio
async def test_karaoke_service_fails_fast_when_demucs_unhealthy(db_session):
    """Karaoke processing should fail immediately when Demucs health is bad."""
    queue_service = QueueService()
    item = queue_service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="kara-offline",
            title="Kara Offline",
            is_karaoke=True,
            burn_lyrics=False,
        ),
    )

    service = KaraokeService()
    service.queue_service = queue_service
    service.youtube_service = Mock()
    service.demucs_client = Mock()
    service.demucs_client.health_check.return_value = DemucsHealthResponse(
        api_url="http://127.0.0.1:8002",
        healthy=False,
        detail="connection refused",
    )

    await service.process_queue_item(db_session, item.id)

    service.youtube_service.download_video.assert_not_called()
    service.youtube_service.download_audio.assert_not_called()

    updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
    assert updated_item is not None
    assert updated_item.status == QueueStatus.FAILED
    assert "Demucs unavailable" in (updated_item.error or "")


def test_queue_service_ordering_helpers(db_session):
    """Queue ordering helpers should support sparse insertion and renumbering."""
    service = QueueService()
    first = service.add_to_queue(
        db_session, QueueItemCreate(youtube_id="o1", title="One", is_karaoke=False)
    )
    second = service.add_to_queue(
        db_session, QueueItemCreate(youtube_id="o2", title="Two", is_karaoke=False)
    )
    assert first.position == 1000
    assert second.position == 2000

    front_position = service.add_to_front(db_session)
    front_item = QueueItem(
        media_id=(
            db_session.query(QueueItem).filter(QueueItem.id == first.id).first().media_id
        ),
        position=front_position,
        requested_karaoke=False,
        requested_burn_lyrics=False,
        status=QueueStatus.PENDING,
    )
    db_session.add(front_item)
    db_session.commit()
    assert front_item.position < first.position

    between = service.insert_between(db_session, first.position, second.position)
    assert first.position < between < second.position

    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    second_row = db_session.query(QueueItem).filter(QueueItem.id == second.id).first()
    first_row.position = 1000
    second_row.position = 1001
    db_session.commit()
    service.renumber_queue_if_needed(db_session)
    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    second_row = db_session.query(QueueItem).filter(QueueItem.id == second.id).first()
    assert second_row.position - first_row.position == 1000


def test_lyrics_service_parse():
    """Test lyrics parsing."""
    service = LyricsService()
    lyrics = "Line 1\nLine 2\n\nLine 3\n"

    lines = service.parse_lyrics_to_lines(lyrics)

    assert len(lines) == 3
    assert lines[0] == "Line 1"
    assert lines[1] == "Line 2"
    assert lines[2] == "Line 3"


@pytest.mark.asyncio
async def test_demucs_client_upload_and_save(tmp_path):
    """Demucs client should upload source audio and save returned no_vocals wav."""
    src = tmp_path / "input.wav"
    src.write_bytes(b"fake-audio-bytes")

    class FakeResponse:
        def __init__(self):
            self.status_code = 200
            self.content = b"no-vocals-wav"
            self.headers = {"X-Job-Id": "job123", "X-Vocals-Path": "C:\\\\vocals.wav"}

        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, files, data):
            assert url.endswith("/separate")
            assert "file" in files
            assert data["model"] == "htdemucs"
            assert data["device"] == "cuda"
            assert data["output_format"] == "wav"
            return FakeResponse()

    from services import demucs_client as dc_module

    original_client = dc_module.httpx.AsyncClient
    original_cache = dc_module.settings.cache_path
    original_demucs_model = dc_module.settings.demucs_model
    original_demucs_device = dc_module.settings.demucs_device
    original_demucs_output_format = dc_module.settings.demucs_output_format
    original_demucs_mp3_bitrate = dc_module.settings.demucs_mp3_bitrate
    try:
        dc_module.httpx.AsyncClient = FakeAsyncClient
        dc_module.settings.cache_path = tmp_path
        dc_module.settings.demucs_model = "htdemucs"
        dc_module.settings.demucs_device = "cuda"
        dc_module.settings.demucs_output_format = "wav"
        dc_module.settings.demucs_mp3_bitrate = 320
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        result = await client.separate_vocals(src)
    finally:
        dc_module.httpx.AsyncClient = original_client
        dc_module.settings.cache_path = original_cache
        dc_module.settings.demucs_model = original_demucs_model
        dc_module.settings.demucs_device = original_demucs_device
        dc_module.settings.demucs_output_format = original_demucs_output_format
        dc_module.settings.demucs_mp3_bitrate = original_demucs_mp3_bitrate

    assert result.no_vocals_path.endswith("_job123_no_vocals.wav")
    saved = Path(result.no_vocals_path)
    assert saved.exists()
    assert saved.read_bytes() == b"no-vocals-wav"


def test_demucs_client_health_check_reports_degraded_payload():
    """Demucs health should parse degraded payload and surface detail."""
    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "degraded", "detail": "demucs cli unavailable"}

    with patch("services.demucs_client.httpx.get", return_value=FakeResponse()):
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        health = client.health_check()

    assert health.healthy is False
    assert "demucs cli unavailable" in health.detail


def test_demucs_client_health_check_uses_short_timeout():
    """Demucs health check should fail fast on unreachable endpoints."""
    expected_timeout = DemucsClient.HEALTH_TIMEOUT_SECONDS
    with patch(
        "services.demucs_client.httpx.get",
        side_effect=httpx.TimeoutException("timed out"),
    ) as mock_get:
        client = DemucsClient(api_url="http://127.0.0.1:8002")
        health = client.health_check()

    mock_get.assert_called_once_with(
        "http://127.0.0.1:8002/health",
        timeout=expected_timeout,
    )
    assert health.healthy is False
    assert health.detail == "Health check timed out"


def test_runtime_settings_get_settings_is_non_blocking():
    """Settings snapshot should not call external health checks."""
    service = RuntimeSettingsService()
    with patch.object(
        RuntimeSettingsService,
        "get_demucs_health",
        side_effect=AssertionError("health check should not be called"),
    ):
        result = service.get_settings()

    assert result.demucs_healthy is False
    assert result.demucs_health_detail == "Health check pending"
    assert result.demucs_model == settings.demucs_model
    assert result.demucs_device == settings.demucs_device
    assert result.demucs_output_format == settings.demucs_output_format
    assert result.demucs_mp3_bitrate == settings.demucs_mp3_bitrate


def test_runtime_settings_update_settings_includes_demucs_health():
    """Updating settings should still return current Demucs health."""
    service = RuntimeSettingsService()
    with patch.object(
        RuntimeSettingsService,
        "get_demucs_health",
        return_value=DemucsHealthResponse(
            api_url="http://127.0.0.1:8001",
            healthy=True,
            detail="Demucs service is healthy",
        ),
    ):
        result = service.update_settings(RuntimeSettingsUpdateRequest())

    assert result.demucs_healthy is True
    assert result.demucs_health_detail == "Demucs service is healthy"


def test_runtime_settings_update_settings_accepts_media_and_cache_paths(tmp_path):
    """Updating runtime settings should accept configurable media/cache paths."""
    service = RuntimeSettingsService()
    media_path = tmp_path / "media"
    cache_path = tmp_path / "cache"

    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        with patch.object(
            RuntimeSettingsService,
            "get_demucs_health",
            return_value=DemucsHealthResponse(
                api_url="http://127.0.0.1:8001",
                healthy=True,
                detail="Demucs service is healthy",
            ),
        ):
            result = service.update_settings(
                RuntimeSettingsUpdateRequest(
                    media_path=str(media_path),
                    cache_path=str(cache_path),
                )
            )

        assert result.media_path == str(media_path)
        assert result.cache_path == str(cache_path)
        assert media_path.exists()
        assert cache_path.exists()
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_runtime_settings_update_settings_accepts_demucs_advanced_fields():
    """Runtime settings should accept demucs model/device/output/bitrate values."""
    service = RuntimeSettingsService()
    original_model = settings.demucs_model
    original_device = settings.demucs_device
    original_output = settings.demucs_output_format
    original_bitrate = settings.demucs_mp3_bitrate
    try:
        with patch.object(
            RuntimeSettingsService,
            "get_demucs_health",
            return_value=DemucsHealthResponse(
                api_url="http://127.0.0.1:8001",
                healthy=True,
                detail="Demucs service is healthy",
            ),
        ):
            result = service.update_settings(
                RuntimeSettingsUpdateRequest(
                    demucs_model="htdemucs_ft",
                    demucs_device="cpu",
                    demucs_output_format="mp3",
                    demucs_mp3_bitrate=256,
                )
            )
        assert result.demucs_model == "htdemucs_ft"
        assert result.demucs_device == "cpu"
        assert result.demucs_output_format == "mp3"
        assert result.demucs_mp3_bitrate == 256
    finally:
        settings.demucs_model = original_model
        settings.demucs_device = original_device
        settings.demucs_output_format = original_output
        settings.demucs_mp3_bitrate = original_bitrate


def test_runtime_settings_update_settings_rejects_invalid_demucs_fields():
    """Runtime settings should validate demucs advanced fields."""
    service = RuntimeSettingsService()
    with pytest.raises(ValueError, match="demucs_device"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_device="gpu"))
    with pytest.raises(ValueError, match="demucs_output_format"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_output_format="flac"))
    with pytest.raises(ValueError, match="demucs_mp3_bitrate"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_mp3_bitrate=32))


def test_runtime_settings_update_settings_rejects_empty_media_path():
    """Runtime settings should reject blank media path values."""
    service = RuntimeSettingsService()
    with pytest.raises(ValueError, match="media_path cannot be empty"):
        service.update_settings(RuntimeSettingsUpdateRequest(media_path=" "))


def test_runtime_settings_update_settings_accepts_proxy_url():
    """Runtime settings should accept valid yt-dlp proxy URLs."""
    service = RuntimeSettingsService()
    original_proxy = settings.ytdlp_proxy_url
    try:
        with patch.object(
            RuntimeSettingsService,
            "get_demucs_health",
            return_value=DemucsHealthResponse(
                api_url="http://127.0.0.1:8001",
                healthy=True,
                detail="Demucs service is healthy",
            ),
        ):
            result = service.update_settings(
                RuntimeSettingsUpdateRequest(
                    ytdlp_proxy_url="http://user:pass@127.0.0.1:8080"
                )
            )
        assert result.ytdlp_proxy_url == "http://user:pass@127.0.0.1:8080"
    finally:
        settings.ytdlp_proxy_url = original_proxy


def test_runtime_settings_update_settings_accepts_empty_proxy_url():
    """Runtime settings should allow clearing yt-dlp proxy URL."""
    service = RuntimeSettingsService()
    original_proxy = settings.ytdlp_proxy_url
    try:
        settings.ytdlp_proxy_url = "socks5://127.0.0.1:1080"
        with patch.object(
            RuntimeSettingsService,
            "get_demucs_health",
            return_value=DemucsHealthResponse(
                api_url="http://127.0.0.1:8001",
                healthy=True,
                detail="Demucs service is healthy",
            ),
        ):
            result = service.update_settings(
                RuntimeSettingsUpdateRequest(ytdlp_proxy_url=" ")
            )
        assert result.ytdlp_proxy_url == ""
    finally:
        settings.ytdlp_proxy_url = original_proxy


def test_runtime_settings_update_settings_rejects_invalid_proxy_url():
    """Runtime settings should reject invalid yt-dlp proxy URLs."""
    service = RuntimeSettingsService()
    with pytest.raises(ValueError, match="ytdlp_proxy_url"):
        service.update_settings(RuntimeSettingsUpdateRequest(ytdlp_proxy_url="proxy.local:8080"))
    with pytest.raises(ValueError, match="ytdlp_proxy_url"):
        service.update_settings(RuntimeSettingsUpdateRequest(ytdlp_proxy_url="ftp://proxy.local:21"))


def test_runtime_settings_get_ytdlp_version():
    """yt-dlp version check should return parsed version string."""
    service = RuntimeSettingsService()
    with patch("services.runtime_settings_service.subprocess.run") as mock_run:
        mock_run.return_value = Mock(stdout="2026.03.15\n")
        result = service.get_ytdlp_version()
    assert result.version == "2026.03.15"
    assert result.binary_path == settings.ytdlp_path


def test_runtime_settings_update_ytdlp_reports_updated():
    """yt-dlp update should report updated when version changes."""
    service = RuntimeSettingsService()
    with patch.object(
        RuntimeSettingsService,
        "get_ytdlp_version",
        side_effect=[
            Mock(version="2026.03.01", binary_path="/usr/bin/yt-dlp"),
            Mock(version="2026.03.15", binary_path="/usr/bin/yt-dlp"),
        ],
    ):
        with patch("services.runtime_settings_service.subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="Updated yt-dlp")
            result = service.update_ytdlp()
    assert result.updated is True
    assert result.before_version == "2026.03.01"
    assert result.after_version == "2026.03.15"


def test_runtime_settings_update_ytdlp_reports_up_to_date():
    """yt-dlp update should report no change when version is unchanged."""
    service = RuntimeSettingsService()
    with patch.object(
        RuntimeSettingsService,
        "get_ytdlp_version",
        side_effect=[
            Mock(version="2026.03.15", binary_path="/usr/bin/yt-dlp"),
            Mock(version="2026.03.15", binary_path="/usr/bin/yt-dlp"),
        ],
    ):
        with patch("services.runtime_settings_service.subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="yt-dlp is up to date")
            result = service.update_ytdlp()
    assert result.updated is False
    assert result.before_version == "2026.03.15"
    assert result.after_version == "2026.03.15"


def test_runtime_settings_update_settings_accepts_concurrent_search_toggle():
    """Runtime settings should accept concurrent search boolean updates."""
    service = RuntimeSettingsService()
    original_value = settings.concurrent_ytdlp_search_enabled
    try:
        with patch.object(
            RuntimeSettingsService,
            "get_demucs_health",
            return_value=DemucsHealthResponse(
                api_url="http://127.0.0.1:8001",
                healthy=True,
                detail="Demucs service is healthy",
            ),
        ):
            result = service.update_settings(
                RuntimeSettingsUpdateRequest(concurrent_ytdlp_search_enabled=True)
            )
        assert result.concurrent_ytdlp_search_enabled is True
    finally:
        settings.concurrent_ytdlp_search_enabled = original_value


def test_runtime_settings_update_settings_persists_to_database(db_session):
    """Updating settings with a DB session should persist selected values."""
    service = RuntimeSettingsService()
    original_stage_qr_url = settings.stage_qr_url
    original_concurrent = settings.concurrent_ytdlp_search_enabled
    try:
        with patch.object(
            RuntimeSettingsService,
            "get_demucs_health",
            return_value=DemucsHealthResponse(
                api_url="http://127.0.0.1:8001",
                healthy=True,
                detail="Demucs service is healthy",
            ),
        ):
            result = service.update_settings(
                RuntimeSettingsUpdateRequest(
                    concurrent_ytdlp_search_enabled=True,
                    stage_qr_url="https://karaoke.test/stage",
                ),
                db_session,
            )

        assert result.concurrent_ytdlp_search_enabled is True
        assert result.stage_qr_url == "https://karaoke.test/stage"

        stored = {
            row.key: row.value
            for row in db_session.query(RuntimeSetting).all()
        }
        assert stored["concurrent_ytdlp_search_enabled"] == "true"
        assert stored["stage_qr_url"] == "https://karaoke.test/stage"
    finally:
        settings.stage_qr_url = original_stage_qr_url
        settings.concurrent_ytdlp_search_enabled = original_concurrent


def test_runtime_settings_load_persisted_settings_applies_db_values(db_session):
    """Persisted settings should be applied on startup when env does not override them."""
    service = RuntimeSettingsService()
    original_values = {
        field: getattr(settings, field)
        for field in RuntimeSettingsService.PERSISTED_SETTING_FIELDS
    }
    try:
        db_session.add_all(
            [
                RuntimeSetting(key="demucs_model", value="persisted-model"),
                RuntimeSetting(key="stage_qr_url", value="https://karaoke.test/stage"),
                RuntimeSetting(key="ffmpeg_preset", value="veryslow"),
            ]
        )
        db_session.commit()

        settings.demucs_model = "temporary-model"
        settings.stage_qr_url = ""

        applied = service.load_persisted_settings(db_session)

        assert "demucs_model" in applied
        assert "stage_qr_url" in applied
        assert settings.demucs_model == "persisted-model"
        assert settings.stage_qr_url == "https://karaoke.test/stage"

        explicit_field = next(
            field
            for field in RuntimeSettingsService.PERSISTED_SETTING_FIELDS
            if field in EXPLICIT_SETTINGS_FIELDS
        )
        assert getattr(settings, explicit_field) == original_values[explicit_field]
    finally:
        for field, value in original_values.items():
            setattr(settings, field, value)


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_concurrent_staggered_when_enabled(mock_ytdlp):
    """Concurrent mode should stagger normal and karaoke-appended results."""
    original_enabled = settings.concurrent_ytdlp_search_enabled
    settings.concurrent_ytdlp_search_enabled = True
    mock_instance = Mock()
    mock_instance.search.side_effect = [
        [
            {"video_id": "n1", "title": "Normal 1", "channel": "C", "thumbnail": "t1"},
            {"video_id": "n2", "title": "Normal 2", "channel": "C", "thumbnail": "t2"},
        ],
        [
            {"video_id": "k1", "title": "Karaoke 1", "channel": "C", "thumbnail": "t3"},
            {"video_id": "k2", "title": "Karaoke 2", "channel": "C", "thumbnail": "t4"},
        ],
    ]
    mock_ytdlp.return_value = mock_instance
    try:
        service = YouTubeService()
        results = service.search("queen bohemian", max_results=4)
    finally:
        settings.concurrent_ytdlp_search_enabled = original_enabled
    assert [r.video_id for r in results] == ["n1", "k1", "n2", "k2"]
    assert mock_instance.search.call_count == 2


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_single_when_query_has_karaoke(mock_ytdlp):
    """Concurrent mode should bypass when query already contains karaoke."""
    original_enabled = settings.concurrent_ytdlp_search_enabled
    settings.concurrent_ytdlp_search_enabled = True
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {"video_id": "a1", "title": "Result", "channel": "C", "thumbnail": "t1"}
    ]
    mock_ytdlp.return_value = mock_instance
    try:
        service = YouTubeService()
        results = service.search("queen karaoke", max_results=5)
    finally:
        settings.concurrent_ytdlp_search_enabled = original_enabled
    assert [r.video_id for r in results] == ["a1"]
    assert mock_instance.search.call_count == 1


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_single_when_feature_disabled(mock_ytdlp):
    """Feature disabled should keep single-search behavior."""
    original_enabled = settings.concurrent_ytdlp_search_enabled
    settings.concurrent_ytdlp_search_enabled = False
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {"video_id": "a1", "title": "Result", "channel": "C", "thumbnail": "t1"}
    ]
    mock_ytdlp.return_value = mock_instance
    try:
        service = YouTubeService()
        service.search("queen bohemian", max_results=5)
    finally:
        settings.concurrent_ytdlp_search_enabled = original_enabled
    assert mock_instance.search.call_count == 1


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_concurrent_dedupes_video_ids(mock_ytdlp):
    """Interleaved concurrent results should dedupe repeated video ids."""
    original_enabled = settings.concurrent_ytdlp_search_enabled
    settings.concurrent_ytdlp_search_enabled = True
    mock_instance = Mock()
    mock_instance.search.side_effect = [
        [
            {"video_id": "same", "title": "Normal", "channel": "C", "thumbnail": "t1"},
            {"video_id": "n2", "title": "Normal 2", "channel": "C", "thumbnail": "t2"},
        ],
        [
            {"video_id": "same", "title": "Karaoke", "channel": "C", "thumbnail": "t3"},
            {"video_id": "k2", "title": "Karaoke 2", "channel": "C", "thumbnail": "t4"},
        ],
    ]
    mock_ytdlp.return_value = mock_instance
    try:
        service = YouTubeService()
        results = service.search("query", max_results=10)
    finally:
        settings.concurrent_ytdlp_search_enabled = original_enabled
    assert [r.video_id for r in results] == ["same", "n2", "k2"]


def test_queue_service_build_media_url_for_media_and_cache(tmp_path):
    """Queue service should map filesystem paths to stable API URLs."""
    service = QueueService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.ensure_paths()

        media_file = settings.media_path / "karaoke.webm"
        cache_file = settings.cache_path / "out" / "mix.mp4"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_text("x", encoding="utf-8")
        cache_file.write_text("y", encoding="utf-8")

        assert service.build_media_url(media_file) == "/media/karaoke.webm"
        assert service.build_media_url(cache_file) == "/cache/out/mix.mp4"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
