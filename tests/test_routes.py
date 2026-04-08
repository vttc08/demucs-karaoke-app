"""Tests for API routes."""
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app
from database import get_db
from models import Base, DemucsHealthResponse, QueueItem, QueueStatus, RuntimeSetting
from config import settings

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for tests."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def client():
    """Create test client and database."""
    original_demucs_api_url = settings.demucs_api_url
    original_demucs_model = settings.demucs_model
    original_demucs_device = settings.demucs_device
    original_demucs_output_format = settings.demucs_output_format
    original_demucs_mp3_bitrate = settings.demucs_mp3_bitrate
    original_ffmpeg_preset = settings.ffmpeg_preset
    original_ffmpeg_crf = settings.ffmpeg_crf
    original_ytdlp_path = settings.ytdlp_path
    original_ytdlp_proxy_url = settings.ytdlp_proxy_url
    original_ffmpeg_path = settings.ffmpeg_path
    original_media_path = settings.media_path
    original_cache_path = settings.cache_path
    original_stage_qr_url = settings.stage_qr_url

    Base.metadata.create_all(bind=engine)
    yield TestClient(app)
    settings.demucs_api_url = original_demucs_api_url
    settings.demucs_model = original_demucs_model
    settings.demucs_device = original_demucs_device
    settings.demucs_output_format = original_demucs_output_format
    settings.demucs_mp3_bitrate = original_demucs_mp3_bitrate
    settings.ffmpeg_preset = original_ffmpeg_preset
    settings.ffmpeg_crf = original_ffmpeg_crf
    settings.ytdlp_path = original_ytdlp_path
    settings.ytdlp_proxy_url = original_ytdlp_proxy_url
    settings.ffmpeg_path = original_ffmpeg_path
    settings.media_path = original_media_path
    settings.cache_path = original_cache_path
    settings.stage_qr_url = original_stage_qr_url
    Base.metadata.drop_all(bind=engine)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_add_to_queue(client):
    """Test adding item to queue."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test123",
            "title": "Test Song",
            "artist": "Test Artist",
            "is_karaoke": True,
            "burn_lyrics": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["youtube_id"] == "test123"
    assert data["title"] == "Test Song"
    assert data["is_karaoke"] is True
    assert data["burn_lyrics"] is True
    assert data["status"] == "pending"


def test_add_to_queue_non_karaoke_forces_burn_lyrics_false(client):
    """Non-karaoke queue items should not keep burn_lyrics enabled."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test124",
            "title": "Test Song 2",
            "is_karaoke": False,
            "burn_lyrics": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_karaoke"] is False
    assert data["burn_lyrics"] is False


def test_get_empty_queue(client):
    """Test getting empty queue."""
    response = client.get("/api/queue/")
    assert response.status_code == 200
    assert response.json() == []


def test_get_queue_with_items(client):
    """Test getting queue with items."""
    # Add items
    client.post(
        "/api/queue/",
        json={
            "youtube_id": "test1",
            "title": "Song 1",
            "is_karaoke": False,
        },
    )
    client.post(
        "/api/queue/",
        json={
            "youtube_id": "test2",
            "title": "Song 2",
            "is_karaoke": True,
        },
    )

    # Get queue
    response = client.get("/api/queue/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Song 1"
    assert data[1]["title"] == "Song 2"


def test_get_current_item_empty(client):
    """Test getting current item when queue is empty."""
    response = client.get("/api/queue/current")
    assert response.status_code == 200
    assert response.json() is None


def test_get_next_item_empty(client):
    """Test getting next item when queue is empty."""
    response = client.get("/api/queue/next")
    assert response.status_code == 200
    assert response.json() is None


def test_queue_page_loads(client):
    """Test queue page renders."""
    response = client.get("/queue")
    assert response.status_code == 200
    assert b"Karaoke Queue" in response.content


def test_stage_page_loads(client):
    """Test stage page renders."""
    response = client.get("/stage")
    assert response.status_code == 200
    assert b"Stage View" in response.content
    assert b"Queue Empty" in response.content or b"Now Playing" in response.content


def test_playback_page_is_removed(client):
    """Legacy playback page should no longer be exposed."""
    response = client.get("/playback")
    assert response.status_code == 404


def test_settings_page_loads(client):
    """Test settings page renders."""
    response = client.get("/settings")
    assert response.status_code == 200
    assert b"Engine Settings" in response.content


def test_get_runtime_settings(client):
    """Runtime settings endpoint should return current values."""
    response = client.get("/api/settings/")
    assert response.status_code == 200
    data = response.json()
    assert "demucs_api_url" in data
    assert "demucs_model" in data
    assert "demucs_device" in data
    assert "demucs_output_format" in data
    assert "demucs_mp3_bitrate" in data
    assert "ffmpeg_preset" in data
    assert "ffmpeg_crf" in data
    assert "ytdlp_path" in data
    assert "ytdlp_proxy_url" in data
    assert "concurrent_ytdlp_search_enabled" in data
    assert "ffmpeg_path" in data
    assert "media_path" in data
    assert "cache_path" in data
    assert "demucs_healthy" in data
    assert "demucs_health_detail" in data
    assert "stage_qr_url" in data


def test_update_runtime_settings(client):
    """Runtime settings endpoint should apply updates."""
    response = client.patch(
        "/api/settings/",
        json={
            "demucs_api_url": "http://127.0.0.1:9001",
            "demucs_model": "htdemucs_ft",
            "demucs_device": "cpu",
            "demucs_output_format": "mp3",
            "demucs_mp3_bitrate": 256,
            "ffmpeg_preset": "superfast",
            "ffmpeg_crf": 28,
            "media_path": "/tmp/karaoke_media_test",
            "cache_path": "/tmp/karaoke_cache_test",
            "ytdlp_path": "yt-dlp",
            "ytdlp_proxy_url": "socks5://127.0.0.1:1080",
            "concurrent_ytdlp_search_enabled": True,
            "ffmpeg_path": "ffmpeg",
            "stage_qr_url": "https://karaoke.test/queue",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["demucs_api_url"] == "http://127.0.0.1:9001"
    assert data["demucs_model"] == "htdemucs_ft"
    assert data["demucs_device"] == "cpu"
    assert data["demucs_output_format"] == "mp3"
    assert data["demucs_mp3_bitrate"] == 256
    assert data["ffmpeg_preset"] == "superfast"
    assert data["ffmpeg_crf"] == 28
    assert data["media_path"] == "/tmp/karaoke_media_test"
    assert data["cache_path"] == "/tmp/karaoke_cache_test"
    assert data["ytdlp_proxy_url"] == "socks5://127.0.0.1:1080"
    assert data["concurrent_ytdlp_search_enabled"] is True
    assert data["stage_qr_url"] == "https://karaoke.test/queue"
    assert "demucs_healthy" in data
    assert "demucs_health_detail" in data


def test_update_runtime_settings_persists_to_database(client):
    """Runtime settings updates should be written to the database."""
    with patch(
        "routes.settings.runtime_settings_service.get_demucs_health",
        return_value=DemucsHealthResponse(
            api_url="http://127.0.0.1:9001",
            healthy=True,
            detail="Demucs service is healthy",
        ),
    ):
        response = client.patch(
            "/api/settings/",
            json={
                "stage_qr_url": "https://karaoke.test/queue",
                "concurrent_ytdlp_search_enabled": True,
            },
        )
    assert response.status_code == 200

    db = TestingSessionLocal()
    try:
        stage_qr = db.query(RuntimeSetting).filter(RuntimeSetting.key == "stage_qr_url").first()
        concurrent = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "concurrent_ytdlp_search_enabled"
        ).first()
        assert stage_qr is not None
        assert stage_qr.value == "https://karaoke.test/queue"
        assert concurrent is not None
        assert concurrent.value == "true"
    finally:
        db.close()


def test_get_demucs_health(client):
    """Demucs health endpoint returns current health state."""
    response = client.get("/api/settings/demucs-health")
    assert response.status_code == 200
    data = response.json()
    assert "api_url" in data
    assert "healthy" in data
    assert "detail" in data


def test_get_ytdlp_version(client):
    """yt-dlp version endpoint should return current version."""
    with patch(
        "routes.settings.runtime_settings_service.get_ytdlp_version",
        return_value={"version": "2026.03.01", "binary_path": "/usr/bin/yt-dlp"},
    ):
        response = client.get("/api/settings/ytdlp/version")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "2026.03.01"
    assert data["binary_path"] == "/usr/bin/yt-dlp"


def test_get_ytdlp_version_error(client):
    """yt-dlp version endpoint should map runtime errors to 400."""
    with patch(
        "routes.settings.runtime_settings_service.get_ytdlp_version",
        side_effect=RuntimeError("yt-dlp version check failed"),
    ):
        response = client.get("/api/settings/ytdlp/version")
    assert response.status_code == 400
    assert "yt-dlp version check failed" in response.json()["detail"]


def test_update_ytdlp(client):
    """yt-dlp update endpoint should return update result."""
    with patch(
        "routes.settings.runtime_settings_service.update_ytdlp",
        return_value={
            "before_version": "2026.03.01",
            "after_version": "2026.03.15",
            "updated": True,
            "detail": "Updated yt-dlp to stable@2026.03.15",
        },
    ):
        response = client.post("/api/settings/ytdlp/update")
    assert response.status_code == 200
    data = response.json()
    assert data["before_version"] == "2026.03.01"
    assert data["after_version"] == "2026.03.15"
    assert data["updated"] is True


def test_update_ytdlp_error(client):
    """yt-dlp update endpoint should map runtime errors to 400."""
    with patch(
        "routes.settings.runtime_settings_service.update_ytdlp",
        side_effect=RuntimeError("yt-dlp update failed"),
    ):
        response = client.post("/api/settings/ytdlp/update")
    assert response.status_code == 400
    assert "yt-dlp update failed" in response.json()["detail"]


def test_update_runtime_settings_rejects_invalid_crf(client):
    """Runtime settings endpoint should validate ffmpeg_crf."""
    response = client.patch("/api/settings/", json={"ffmpeg_crf": 60})
    assert response.status_code == 400
    assert "ffmpeg_crf" in response.json()["detail"]


def test_skip_current_promotes_next_ready(client):
    """Test skip endpoint removes current item and promotes next."""
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "first", "title": "First", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "second", "title": "Second", "is_karaoke": True},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        second_row = db.query(QueueItem).filter(QueueItem.id == second["id"]).first()
        first_row.status = QueueStatus.PLAYING
        second_row.status = QueueStatus.READY
        db.commit()
    finally:
        db.close()

    response = client.post("/api/queue/skip")
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data["id"] == second["id"]
    assert data["status"] == "playing"

    db = TestingSessionLocal()
    try:
        assert db.query(QueueItem).filter(QueueItem.id == first["id"]).first() is None
    finally:
        db.close()


def test_skip_current_without_next_returns_none(client):
    """Test skip endpoint when only current playing exists."""
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "only", "title": "Only", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        first_row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    response = client.post("/api/queue/skip")
    assert response.status_code == 200
    assert response.json() is None


def test_complete_current_promotes_next_ready(client):
    """Test complete-current endpoint removes current item and promotes next."""
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "first-c", "title": "First C", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "second-c", "title": "Second C", "is_karaoke": True},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        second_row = db.query(QueueItem).filter(QueueItem.id == second["id"]).first()
        first_row.status = QueueStatus.PLAYING
        second_row.status = QueueStatus.READY
        db.commit()
    finally:
        db.close()

    response = client.post("/api/queue/complete-current")
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data["id"] == second["id"]
    assert data["status"] == "playing"

    db = TestingSessionLocal()
    try:
        assert db.query(QueueItem).filter(QueueItem.id == first["id"]).first() is None
    finally:
        db.close()


def test_complete_current_without_next_returns_none(client):
    """Test complete-current endpoint when only current playing exists."""
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "only-c", "title": "Only C", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        first_row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    response = client.post("/api/queue/complete-current")
    assert response.status_code == 200
    assert response.json() is None


def test_media_file_served_from_media_mount(client):
    """Test files under configured media path are served by app mount."""
    media_file = Path(settings.media_path) / "test-media-file.txt"
    media_file.write_text("ok", encoding="utf-8")
    try:
        response = client.get("/media/test-media-file.txt")
        assert response.status_code == 200
        assert response.text == "ok"
    finally:
        if media_file.exists():
            media_file.unlink()


def test_cache_file_served_from_cache_route(client):
    """Test files under configured cache path are served by /cache route."""
    cache_file = Path(settings.cache_path) / "test-cache-file.txt"
    cache_file.write_text("ok-cache", encoding="utf-8")
    try:
        response = client.get("/cache/test-cache-file.txt")
        assert response.status_code == 200
        assert response.text == "ok-cache"
    finally:
        if cache_file.exists():
            cache_file.unlink()


def test_get_queue_item_lyrics_cues_from_lrc(client):
    """Lyrics cues endpoint should parse LRC sidecar files."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-lrc-1", "title": "Lyric LRC", "is_karaoke": False},
    ).json()

    lyrics_file = Path(settings.media_path) / "route-lyrics.lrc"
    lyrics_file.write_text("[00:00.00]Line one\n[00:03.00]Line two\n", encoding="utf-8")

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        assert row is not None
        assert row.media is not None
        row.media.lyrics_path = "/media/route-lyrics.lrc"
        db.commit()
    finally:
        db.close()

    try:
        response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
        assert response.status_code == 200
        payload = response.json()
        assert payload["item_id"] == created["id"]
        assert payload["source_format"] == "lrc"
        assert payload["cues"][0] == {"time": 0.0, "text": "Line one"}
        assert payload["cues"][1] == {"time": 3.0, "text": "Line two"}
    finally:
        if lyrics_file.exists():
            lyrics_file.unlink()


def test_get_queue_item_lyrics_cues_from_json(client):
    """Lyrics cues endpoint should read JSON sidecar files."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-json-1", "title": "Lyric JSON", "is_karaoke": False},
    ).json()

    lyrics_file = Path(settings.cache_path) / "route-lyrics.json"
    lyrics_file.write_text(
        '{"cues":[{"start":4.0,"line":"Fourth"},{"time":1.5,"text":"First"}]}',
        encoding="utf-8",
    )

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        assert row is not None
        assert row.media is not None
        row.media.lyrics_path = "/cache/route-lyrics.json"
        db.commit()
    finally:
        db.close()

    try:
        response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_format"] == "json"
        assert payload["cues"] == [
            {"time": 1.5, "text": "First"},
            {"time": 4.0, "text": "Fourth"},
        ]
    finally:
        if lyrics_file.exists():
            lyrics_file.unlink()


def test_get_queue_item_lyrics_cues_returns_404_without_lyrics(client):
    """Lyrics cues endpoint should return 404 when no lyrics sidecar exists."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-none-1", "title": "Lyric None", "is_karaoke": False},
    ).json()

    response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
    assert response.status_code == 404
    assert "Lyrics not available" in response.json()["detail"]


def test_websocket_connect_and_receive_connected_message(client):
    """WebSocket endpoint should accept connections and send initial connected payload."""
    with client.websocket_connect("/api/queue/ws") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "connected"
        assert "connection_count" in message["data"]


def test_websocket_broadcasts_queue_item_added_event(client):
    """Adding a queue item should broadcast queue_item_added to websocket clients."""
    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        response = client.post(
            "/api/queue/",
            json={"youtube_id": "ws-add", "title": "WS Add", "is_karaoke": False},
        )
        assert response.status_code == 200
        item = response.json()

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "queue_item_added"
        assert event["data"]["id"] == item["id"]
        assert event["data"]["title"] == "WS Add"


def test_websocket_broadcasts_queue_item_removed_event(client):
    """Deleting a queue item should broadcast queue_item_removed."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-del", "title": "WS Remove", "is_karaoke": False},
    ).json()

    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        response = client.delete(f"/api/queue/{created['id']}")
        assert response.status_code == 200

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "queue_item_removed"
        assert event["data"]["id"] == created["id"]


def test_websocket_broadcasts_current_item_changed_on_skip(client):
    """Skipping current item should broadcast current_item_changed."""
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-skip-1", "title": "WS Skip 1", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-skip-2", "title": "WS Skip 2", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        second_row = db.query(QueueItem).filter(QueueItem.id == second["id"]).first()
        first_row.status = QueueStatus.PLAYING
        second_row.status = QueueStatus.READY
        db.commit()
    finally:
        db.close()

    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        response = client.post("/api/queue/skip")
        assert response.status_code == 200

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "current_item_changed"
        assert event["data"]["id"] == second["id"]
        assert event["data"]["previous_id"] == first["id"]


def test_websocket_broadcasts_queue_cleared(client):
    """Clearing queue should broadcast queue_cleared."""
    client.post(
        "/api/queue/",
        json={"youtube_id": "ws-clear-1", "title": "WS Clear 1", "is_karaoke": False},
    )
    client.post(
        "/api/queue/",
        json={"youtube_id": "ws-clear-2", "title": "WS Clear 2", "is_karaoke": False},
    )

    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        response = client.post("/api/queue/clear")
        assert response.status_code == 200

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "queue_cleared"


def test_websocket_stage_command_pause_broadcasts_control_and_state(client):
    """Pause stage command should broadcast control command and paused state."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "pause", "source": "queue"},
                    "timestamp": 123,
                }
            )

            control_event = receiver.receive_json()
            if control_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                control_event = receiver.receive_json()
            assert control_event["type"] == "stage_control_command"
            assert control_event["data"]["command"] == "pause"
            assert control_event["data"]["source"] == "queue"

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["is_paused"] is True
            assert state_event["data"]["vocals_enabled"] is True
            assert state_event["data"]["vocals_volume"] == 1.0


def test_websocket_stage_command_seek_broadcasts_control_and_state(client):
    """Seek stage command should broadcast target timestamp and paused state."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "seek",
                        "source": "queue",
                        "seek_time": 42.5,
                        "is_paused": False,
                    },
                    "timestamp": 123,
                }
            )

            control_event = receiver.receive_json()
            if control_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                control_event = receiver.receive_json()
            assert control_event["type"] == "stage_control_command"
            assert control_event["data"]["command"] == "seek"
            assert control_event["data"]["source"] == "queue"
            assert control_event["data"]["seek_time"] == 42.5
            assert control_event["data"]["is_paused"] is False

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["is_paused"] is False


def test_websocket_stage_command_seek_rejects_invalid_time(client):
    """Invalid seek_time values should return websocket error."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        sender.send_json(
            {
                "type": "stage_command",
                "data": {"command": "seek", "source": "queue", "seek_time": -1},
                "timestamp": 123,
            }
        )

        response = sender.receive_json()
        if response["type"] == "ping":
            sender.send_json({"type": "pong"})
            response = sender.receive_json()
        assert response["type"] == "error"
        assert "seek_time must be a non-negative finite number" in response["data"]["detail"]


def test_websocket_stage_command_resync_broadcasts_control(client):
    """Resync stage command should broadcast control command."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "resync", "source": "queue"},
                    "timestamp": 123,
                }
            )

            control_event = receiver.receive_json()
            if control_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                control_event = receiver.receive_json()
            assert control_event["type"] == "stage_control_command"
            assert control_event["data"]["command"] == "resync"
            assert control_event["data"]["source"] == "queue"


def test_websocket_stage_command_set_vocals_enabled_broadcasts_state(client):
    """Vocals enabled command should broadcast updated stage mix state."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "set_vocals_enabled", "source": "queue", "vocals_enabled": False},
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["vocals_enabled"] is False
            assert state_event["data"]["vocals_volume"] == 1.0


def test_websocket_stage_command_set_vocals_volume_broadcasts_state(client):
    """Vocals volume command should broadcast updated stage mix state."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "set_vocals_enabled", "source": "queue", "vocals_enabled": True},
                    "timestamp": 122,
                }
            )
            bootstrap_event = receiver.receive_json()
            if bootstrap_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                bootstrap_event = receiver.receive_json()
            assert bootstrap_event["type"] == "stage_state_update"
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "set_vocals_volume", "source": "queue", "vocals_volume": 0.35},
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["vocals_enabled"] is True
            assert state_event["data"]["vocals_volume"] == 0.35


def test_websocket_stage_command_set_vocals_volume_rejects_out_of_bounds(client):
    """Out-of-range vocals volume should return websocket error and not broadcast state."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        sender.send_json(
            {
                "type": "stage_command",
                "data": {"command": "set_vocals_volume", "source": "queue", "vocals_volume": 2.0},
                "timestamp": 123,
            }
        )

        response = sender.receive_json()
        if response["type"] == "ping":
            sender.send_json({"type": "pong"})
            response = sender.receive_json()
        assert response["type"] == "error"
        assert "vocals_volume must be between 0.0 and 1.0" in response["data"]["detail"]


def test_websocket_stage_command_skip_broadcasts_and_changes_current(client):
    """Skip stage command should advance queue and broadcast item change."""
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-stage-skip-1", "title": "WS Stage Skip 1", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-stage-skip-2", "title": "WS Stage Skip 2", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        second_row = db.query(QueueItem).filter(QueueItem.id == second["id"]).first()
        first_row.status = QueueStatus.PLAYING
        second_row.status = QueueStatus.READY
        db.commit()
    finally:
        db.close()

    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {"command": "skip", "source": "queue"},
                    "timestamp": 123,
                }
            )

            stage_control_event = None
            current_changed_event = None
            for _ in range(6):
                event = receiver.receive_json()
                if event["type"] == "ping":
                    receiver.send_json({"type": "pong"})
                    continue
                if event["type"] == "stage_control_command":
                    stage_control_event = event
                if event["type"] == "current_item_changed":
                    current_changed_event = event
                if stage_control_event and current_changed_event:
                    break

            assert stage_control_event is not None
            assert stage_control_event["data"]["command"] == "skip"
            assert stage_control_event["data"]["source"] == "queue"
            assert current_changed_event is not None
            assert current_changed_event["data"]["id"] == second["id"]
            assert current_changed_event["data"]["previous_id"] == first["id"]

    current = client.get("/api/queue/current")
    assert current.status_code == 200
    current_payload = current.json()
    assert current_payload is not None
    assert current_payload["id"] == second["id"]


def test_qr_endpoint_returns_png(client):
    """QR endpoint should respond with PNG data."""
    response = client.get("/api/qr", params={"data": "stage-karaoke", "size": 256})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0
