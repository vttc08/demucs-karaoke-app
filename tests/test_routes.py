"""Tests for API routes."""
import json
import re
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app
from database import ensure_auxiliary_schema, get_db
from models import (
    Base,
    DemucsHealthResponse,
    MediaItem,
    QueueItem,
    QueueStatus,
    RuntimeSetting,
)
from services import lyrics_service as lyrics_service_module
from services.auth_service import ADMIN_SESSION_COOKIE, AuthService
from services.i18n_service import LOCALE_COOKIE
from services.media_naming import build_media_stem
from services.media_thumbnail_service import MediaThumbnailService
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
    original_lyrics_provider_netease_enabled = settings.lyrics_provider_netease_enabled
    original_lyrics_provider_lrclib_enabled = settings.lyrics_provider_lrclib_enabled
    original_ffmpeg_path = settings.ffmpeg_path
    original_media_path = settings.media_path
    original_cache_path = settings.cache_path
    original_stage_qr_url = settings.stage_qr_url
    original_stage_lobby_media_path = settings.stage_lobby_media_path

    Base.metadata.create_all(bind=engine)
    ensure_auxiliary_schema(engine)
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
    settings.lyrics_provider_netease_enabled = original_lyrics_provider_netease_enabled
    settings.lyrics_provider_lrclib_enabled = original_lyrics_provider_lrclib_enabled
    settings.ffmpeg_path = original_ffmpeg_path
    settings.media_path = original_media_path
    settings.cache_path = original_cache_path
    settings.stage_qr_url = original_stage_qr_url
    settings.stage_lobby_media_path = original_stage_lobby_media_path
    Base.metadata.drop_all(bind=engine)


def authenticate_admin_client(client: TestClient) -> str:
    """Attach a valid admin session cookie to the test client."""
    service = AuthService()
    with TestingSessionLocal() as db:
        admin = service.create_or_update_admin(
            db, "admin", "correct horse battery staple"
        )
        token, _ = service.create_admin_session(db, admin)
    client.cookies.set(ADMIN_SESSION_COOKIE, token)
    return token


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_search_youtube_marks_downloaded_results(client):
    """Search API should include downloaded markers when library rows exist."""
    with patch("routes.search.youtube_service.search") as mock_search:
        mock_search.return_value = [
            {
                "video_id": "saved123",
                "title": "Already Saved",
                "channel": "Library",
                "duration": "2:00",
                "thumbnail": "https://i.ytimg.com/vi/saved123/hqdefault.jpg",
                "downloaded": True,
            }
        ]
        response = client.get("/api/search/?q=saved123")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["downloaded"] is True
    mock_search.assert_called_once()
    assert "db" in mock_search.call_args.kwargs


def test_search_with_source_local_filter(client):
    """Search with source=local should only call search with source filter."""
    with patch("routes.search.youtube_service.search") as mock_search:
        mock_search.return_value = [
            {
                "source": "local",
                "media_item_id": 1,
                "video_id": None,
                "title": "Local Song",
                "channel": "Local Artist",
                "duration": None,
                "thumbnail": None,
                "downloaded": True,
            }
        ]
        response = client.get("/api/search/?q=test&source=local")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["source"] == "local"
    assert data[0]["media_item_id"] == 1
    mock_search.assert_called_once()
    # Verify source parameter was passed
    call_kwargs = mock_search.call_args.kwargs
    assert call_kwargs.get("source") == "local"


def test_search_with_source_youtube_filter(client):
    """Search with source=youtube should only call search with source filter."""
    with patch("routes.search.youtube_service.search") as mock_search:
        mock_search.return_value = [
            {
                "source": "youtube",
                "media_item_id": None,
                "video_id": "yt123",
                "title": "YouTube Song",
                "channel": "YouTube Channel",
                "duration": "3:45",
                "thumbnail": "https://example.com/thumb.jpg",
                "downloaded": False,
            }
        ]
        response = client.get("/api/search/?q=test&source=youtube")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["source"] == "youtube"
    assert data[0]["video_id"] == "yt123"
    mock_search.assert_called_once()
    # Verify source parameter was passed
    call_kwargs = mock_search.call_args.kwargs
    assert call_kwargs.get("source") == "youtube"


def test_search_with_invalid_source_returns_error(client):
    """Search with invalid source parameter should return 400 error."""
    response = client.get("/api/search/?q=test&source=invalid")
    assert response.status_code == 400
    data = response.json()
    assert "source must be" in data["detail"].lower()


def test_search_without_source_returns_mixed(client):
    """Search without source parameter should return mixed results (default behavior)."""
    with patch("routes.search.youtube_service.search") as mock_search:
        mock_search.return_value = [
            {
                "source": "local",
                "media_item_id": 1,
                "video_id": None,
                "title": "Local Song",
                "channel": "Local Artist",
                "duration": None,
                "thumbnail": None,
                "downloaded": True,
            },
            {
                "source": "youtube",
                "media_item_id": None,
                "video_id": "yt123",
                "title": "YouTube Song",
                "channel": "YouTube Channel",
                "duration": "4:00",
                "thumbnail": "https://example.com/thumb.jpg",
                "downloaded": False,
            },
        ]
        response = client.get("/api/search/?q=test")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["source"] == "local"
    assert data[1]["source"] == "youtube"
    mock_search.assert_called_once()
    # Verify source parameter was None (default)
    call_kwargs = mock_search.call_args.kwargs
    assert call_kwargs.get("source") is None


def test_add_to_queue(client):
    """Test adding item to queue."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test123",
            "title": "Test Song",
            "artist": "Test Artist",
            "is_karaoke": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["youtube_id"] == "test123"
    assert data["title"] == "Test Song"
    assert data["is_karaoke"] is True
    assert data["status"] == "pending"


def test_add_to_queue_uses_guest_cookies_for_requester(client):
    """Queue add should expose requester label from guest cookies."""
    client.cookies.set("karaoke_guest_id", "guest-123")
    client.cookies.set("karaoke_queue_tab_id", "tab-123")
    client.cookies.set("karaoke_singer", "Alex")

    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test123-requester",
            "title": "Requester Song",
            "is_karaoke": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requested_by_name"] == "Alex"

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == data["id"]).first()
        assert row is not None
        assert row.user_id == "guest-123"
        assert row.session_id == "tab-123"
        assert row.requester_name == "Alex"


def test_add_to_queue_rejects_queue_as_name_for_non_admin(client):
    """Non-admin queue adds cannot override requester label via queue_as_name."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-as-guest-denied",
            "title": "Queue As Denied",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "queue_as_name requires an admin session"


def test_add_to_queue_admin_can_override_requester_name(client):
    """Admin queue adds may set queue_as_name without changing ownership metadata."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    client.cookies.set("karaoke_queue_tab_id", "tab-admin-device")
    client.cookies.set("karaoke_singer", "Admin Device")

    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-as-admin-ok",
            "title": "Queue As Admin",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requested_by_name"] == "Taylor"

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == data["id"]).first()
        assert row is not None
        assert row.user_id == "guest-admin-device"
        assert row.session_id == "tab-admin-device"
        assert row.requester_name == "Taylor"


def test_add_to_queue_admin_can_delegate_guest_ownership(client):
    """Admin queue adds may transfer ownership to a selected guest id."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    client.cookies.set("karaoke_queue_tab_id", "tab-admin-device")
    client.cookies.set("karaoke_singer", "Admin Device")

    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-as-admin-delegated",
            "title": "Queue As Delegated",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-target",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requested_by_name"] == "Taylor"

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == data["id"]).first()
        assert row is not None
        assert row.user_id == "guest-target"
        assert row.session_id == "tab-admin-device"
        assert row.requester_name == "Taylor"


def test_add_to_queue_rejects_queue_as_guest_id_for_non_admin(client):
    """Non-admin queue adds cannot set a delegated guest id."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-as-guest-id-denied",
            "title": "Queue As Guest Id Denied",
            "is_karaoke": False,
            "queue_as_guest_id": "guest-target",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "queue_as_guest_id requires an admin session"


def test_add_to_queue_non_karaoke(client):
    """Non-karaoke queue items should be accepted without burn settings."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "test124",
            "title": "Test Song 2",
            "is_karaoke": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_karaoke"] is False


def test_add_to_queue_persists_inline_lyrics_sidecar(client):
    """Queue add should persist inline lyrics so karaoke processing can reuse them."""
    response = client.post(
        "/api/queue/",
        json={
            "youtube_id": "queue-lyrics-1",
            "title": "Queue Lyrics",
            "artist": "Singer",
            "is_karaoke": True,
            "lyrics_text": "[00:01.00]Lyrics line",
        },
    )
    assert response.status_code == 200
    data = response.json()
    expected_stem = build_media_stem("Queue Lyrics", "Singer", fallback="queue-lyrics-1")
    assert data["lyrics_path"] == f"/cache/lyrics/{expected_stem}.lrc"


@pytest.mark.asyncio
async def test_resolve_lyrics_route_returns_payload(client):
    """Lyrics resolve route should surface provider lyrics and inferred metadata."""
    from routes import lyrics as lyrics_routes

    payload = lyrics_service_module.LyricsPayload(
        lyrics="[00:01.00]Resolved line",
        is_synced=True,
        provider="lrclib",
        inferred_song=lyrics_service_module.InferredSong(
            title="Resolved Song",
            artist="Resolved Artist",
            source="regex",
        ),
    )
    with patch.object(lyrics_routes.lyrics_service, "resolve_lyrics", new=AsyncMock(return_value=payload)):
        response = client.post(
            "/api/lyrics/resolve",
            json={"title": "Resolved Song", "artist": "Resolved Artist"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resolved"
    assert data["provider"] == "lrclib"
    assert data["lyrics"] == "[00:01.00]Resolved line"
    assert data["is_synced"] is True


@pytest.mark.asyncio
async def test_resolve_lyrics_route_returns_not_found(client):
    """Lyrics resolve route should still return inferred metadata when providers miss."""
    from routes import lyrics as lyrics_routes

    with patch.object(lyrics_routes.lyrics_service, "resolve_lyrics", new=AsyncMock(return_value=None)):
        with patch.object(
            lyrics_routes.lyrics_service,
            "infer_song_metadata",
            new=AsyncMock(
                return_value=lyrics_service_module.InferredSong(
                    title="Inferred Song",
                    artist="Inferred Artist",
                    source="regex",
                )
            ),
        ):
            response = client.post(
                "/api/lyrics/resolve",
                json={"title": "Raw Song Title", "artist": "Raw Artist"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_found"
    assert data["title"] == "Inferred Song"
    assert data["artist"] == "Inferred Artist"


def test_add_to_queue_with_media_item_id(client):
    """Queue endpoint should enqueue existing local media by media_item_id."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id="local-abc",
            title="Local Track",
            artist="Local Artist",
            media_path="/media/local-abc.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        media_id = media.id

    response = client.post(
        "/api/queue/",
        json={
            "media_item_id": media_id,
            "title": "Local Track",
            "artist": "Local Artist",
            "is_karaoke": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["media_id"] == media_id
    assert data["youtube_id"] == "local-abc"
    assert data["thumbnail"] == "https://i.ytimg.com/vi/local-abc/hqdefault.jpg"


def test_queue_page_renders_thumbnail_for_local_media(client, tmp_path, monkeypatch):
    """Queue page should render cached thumbnails for local media items."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "queue-thumb.mp4"
    media_file.write_bytes(b"media")
    thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(b"thumbnail")

    with TestingSessionLocal() as db:
        media = MediaItem(
            youtube_id=None,
            title="Queue Thumbnail",
            artist="Artist",
            media_path="/media/queue-thumb.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        db.refresh(media)

        queue_item = QueueItem(
            media_id=media.id,
            position=1000,
            requested_karaoke=False,
            status=QueueStatus.PENDING,
        )
        db.add(queue_item)
        db.commit()

    response = client.get("/queue")

    assert response.status_code == 200
    assert MediaThumbnailService.thumbnail_url_for_media_file(media_file) in response.text


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
    assert b'id="queue-singer-name"' in response.content
    assert b'id="singer-name-modal"' in response.content
    assert b"queue-config-modal" in response.content
    assert b"Configure Queue" in response.content
    assert b"queue-toast" in response.content
    assert b"queue-config-lyrics-detail" in response.content
    assert b"flex-none shrink-0" in response.content
    assert 'id="stage-remote-vocals-toggle-btn"' in response.text
    assert 'id="stage-remote-vocals-volume-slider"' in response.text
    assert 'id="stage-remote-vocals-volume-label"' in response.text
    assert 'id="stage-remote-lyrics-toggle-btn"' in response.text
    assert 'id="qr-toggle-btn"' not in response.text
    assert 'id="queue-library-shortcuts"' in response.text
    assert 'href="/media"' in response.text
    assert 'href="/upload"' in response.text
    assert 'href="/queue/lyrics"' in response.text
    assert response.text.index('id="search-input"') < response.text.index('id="stage-remote-play-pause-btn"')
    assert 'id="queue-as-settings-panel"' not in response.text
    assert 'id="queue-config-queue-as-panel"' not in response.text
    assert 'id="clear-all-btn"' not in response.text
    assert "queue-move-up-" not in response.text
    assert "skipToSong(" not in response.text
    assert 'aria-label="Settings"' not in response.text
    assert 'aria-label="Stage"' not in response.text
    assert 'aria-label="Upload"' not in response.text
    assert "shield_person" not in response.text


def test_queue_lyrics_page_loads(client):
    """Queue lyrics page should render the lyrics viewer shell."""
    response = client.get("/queue/lyrics")

    assert response.status_code == 200
    assert "Lyrics Viewer" in response.text
    assert 'id="lyrics-scroll-container"' in response.text
    assert 'id="queue-lyrics-chinese-toggle"' in response.text
    assert 'id="queue-lyrics-pinyin-toggle"' in response.text
    assert "/static/queue_lyrics.js" in response.text
    assert 'href="/queue"' in response.text


def test_queue_page_admin_shows_queue_as_controls(client):
    """Admin queue page should expose queue-as device controls and modal."""
    authenticate_admin_client(client)

    response = client.get("/queue")

    assert response.status_code == 200
    assert 'id="queue-as-settings-panel"' in response.text
    assert 'id="queue-as-enabled-toggle"' in response.text
    assert 'id="queue-as-modal"' in response.text
    assert 'id="queue-config-queue-as-panel"' in response.text
    assert response.text.index('href="/queue/lyrics"') < response.text.index('id="queue-as-settings-panel"')
    assert response.text.index('id="queue-as-settings-panel"') < response.text.index('id="search-results"')


def test_queue_page_renders_simplified_chinese_locale(client):
    """Queue page should use the selected frontend locale cookie."""
    response = client.get("/queue", cookies={LOCALE_COOKIE: "zh-CN"})

    assert response.status_code == 200
    assert '<html class="dark" lang="zh-CN">' in response.text
    assert "卡拉 OK 队列" in response.text
    assert "搜索本地媒体库和 YouTube" in response.text
    assert 'id="language-select"' in response.text


def test_queue_page_renders_requester_label(client):
    """Queue page should render requester labels without template errors."""
    client.cookies.set("karaoke_singer", "Alex")
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "queue-ui-requester", "title": "Requester UI", "is_karaoke": False},
    )
    assert created.status_code == 200

    response = client.get("/queue")

    assert response.status_code == 200
    assert "Requested by Alex" in response.text


def test_queue_page_hides_left_controls_for_guests(client):
    """Guest queue cards should not render the left-side action column."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-left", "title": "Guest Left", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    response = client.get("/queue")

    assert response.status_code == 200
    assert "queue-move-up-" not in response.text
    assert "queue-move-down-" not in response.text
    assert "equalizer" not in response.text


def test_queue_page_shows_guest_remove_only_for_owned_items(client):
    """Guest queue page should render remove only for owned non-playing items."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    owned = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-own-remove", "title": "Guest Owned", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-other")
    other = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-other-remove", "title": "Guest Other", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-owner")
    response = client.get("/queue")

    assert response.status_code == 200
    assert f'onclick="removeSong(\'{owned["id"]}\')"' in response.text
    assert f'onclick="removeSong(\'{other["id"]}\')"' not in response.text


def test_queue_page_uses_dash_in_default_guest_name(client):
    """Default generated guest names should not contain spaces."""
    response = client.get("/queue")

    assert response.status_code == 200
    assert "`${window.KaraokeI18n?.t('common.guest') || 'Guest'}-${Math.floor(1000 + Math.random() * 9000)}`" in response.text


def test_language_route_sets_cookie_and_redirects_locally(client):
    """Language selection should persist in a cookie and return to the requested page."""
    response = client.post(
        "/language",
        data={"language": "zh-CN", "next": "/media"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/media"
    assert response.cookies.get(LOCALE_COOKIE) == "zh-CN"


def test_language_route_rejects_external_redirect_targets(client):
    """Language route should not redirect to external URLs."""
    response = client.post(
        "/language",
        data={"language": "zh-CN", "next": "https://example.com/phish"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/queue"


def test_locale_catalogs_have_matching_keys():
    """Every supported locale should expose the same UI translation keys."""
    locale_dir = Path("locales")
    english_keys = set(json.loads((locale_dir / "en.json").read_text(encoding="utf-8")))
    chinese_keys = set(json.loads((locale_dir / "zh-CN.json").read_text(encoding="utf-8")))

    assert chinese_keys == english_keys


def test_queue_page_shows_admin_queue_controls(client):
    """Admin queue page should show destructive queue controls."""
    authenticate_admin_client(client)
    client.post(
        "/api/queue/",
        json={"youtube_id": "admin-ui-del", "title": "Admin UI Delete", "is_karaoke": False},
    )

    response = client.get("/queue")

    assert response.status_code == 200
    assert 'id="clear-all-btn"' in response.text
    assert 'onclick="removeSong(\'' in response.text
    assert response.text.count('onclick="removeSong(\'') == 1
    assert "queue-move-up-" in response.text
    assert "queue-move-down-" in response.text
    assert "skipToSong(" not in response.text
    assert 'aria-label="Stage"' in response.text
    assert 'aria-label="Settings"' in response.text
    assert 'aria-label="Media"' in response.text
    assert 'aria-label="Upload"' not in response.text


def test_stage_page_requires_admin(client):
    """Guest users should be redirected away from the stage page."""
    response = client.get("/stage", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_stage_page_loads_for_admin(client):
    """Test stage page renders for a valid admin session."""
    authenticate_admin_client(client)
    with patch(
        "routes.pages.stage_lobby_service.resolve_lobby_media_url",
        return_value="/media/stage-lobby-fallback.mp4",
    ):
        response = client.get("/stage")
    assert response.status_code == 200
    assert b"Stage" in response.content
    assert b"Now Playing" in response.content
    assert b'id="stage-video-player"' in response.content


def test_stage_page_renders_audio_mode_for_current_mp3(client, tmp_path):
    """Stage page should bootstrap audio-mode playback for current MP3 items."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    authenticate_admin_client(client)
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "stage-song.mp3"
        media_file.write_bytes(b"audio")
        thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"thumb")

        with TestingSessionLocal() as db:
            media_item = MediaItem(
                title="Stage Audio",
                artist="Stage Artist",
                media_path="/media/stage-song.mp3",
                missing=False,
            )
            db.add(media_item)
            db.flush()
            db.add(
                QueueItem(
                    media_id=media_item.id,
                    position=1000,
                    requested_karaoke=False,
                    status=QueueStatus.PLAYING,
                )
            )
            db.commit()

        with patch(
            "routes.pages.stage_lobby_service.resolve_lobby_media_url",
            return_value="/media/stage-lobby-fallback.mp4",
        ):
            response = client.get("/stage")

        assert response.status_code == 200
        assert b'id="stage-audio-player"' in response.content
        assert b'id="stage-audio-hero"' in response.content
        assert MediaThumbnailService.thumbnail_url_for_media_file(media_file).encode("utf-8") in response.content
        assert re.search(
            rb'<video[^>]*id="stage-video-player"[\s\S]*?<source src="" type="video/mp4">',
            response.content,
        )
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_playback_page_is_removed(client):
    """Legacy playback page should no longer be exposed."""
    response = client.get("/playback")
    assert response.status_code == 404


def test_settings_page_requires_admin(client):
    """Settings page should redirect non-admin guests to admin login."""
    response = client.get("/settings", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_settings_page_loads_for_admin(client):
    """Test settings page renders for a valid admin session."""
    authenticate_admin_client(client)
    response = client.get("/settings")
    assert response.status_code == 200
    assert b"Settings" in response.content
    assert b"Admin session" in response.content
    assert b"Log out" in response.content
    assert b">Save<" in response.content
    assert b">Refresh<" in response.content
    assert b"Admin Access" not in response.content
    assert 'aria-label="Settings"' in response.text
    assert 'aria-label="Media"' in response.text
    assert 'aria-label="Upload"' not in response.text
    assert "shield_person" not in response.text


def test_admin_login_rejects_invalid_credentials(client):
    """Admin login should not grant access without valid DB credentials."""
    response = client.post(
        "/login",
        data={"type": "admin", "username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert ADMIN_SESSION_COOKIE not in response.cookies
    assert "Invalid admin username or password" in response.text


def test_login_page_is_admin_only(client):
    """Login page should not show guest identification controls."""
    response = client.get("/login")

    assert response.status_code == 200
    assert 'id="admin-form"' in response.text
    assert 'id="guest-form"' not in response.text
    assert "Guest" not in response.text
    assert "Continue to guest queue" in response.text


def test_admin_login_sets_db_backed_session_cookie(client):
    """Valid admin login should create an HttpOnly admin session cookie."""
    with TestingSessionLocal() as db:
        AuthService().create_or_update_admin(
            db, "Admin", "correct horse battery staple"
        )

    response = client.post(
        "/login",
        data={
            "type": "admin",
            "username": "admin",
            "password": "correct horse battery staple",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/queue"
    assert ADMIN_SESSION_COOKIE in response.cookies
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()


def test_logout_deletes_admin_session(client):
    """Logout should remove the persisted admin session."""
    service = AuthService()
    with TestingSessionLocal() as db:
        admin = service.create_or_update_admin(
            db, "admin", "correct horse battery staple"
        )
        token, _ = service.create_admin_session(db, admin)

    response = client.get(
        "/logout",
        cookies={ADMIN_SESSION_COOKIE: token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with TestingSessionLocal() as db:
        assert service.get_admin_for_session(db, token) is None


def test_upload_page_loads(client):
    """Test upload page renders with queue toggle and infer button."""
    response = client.get("/upload")
    assert response.status_code == 200
    assert "Upload" in response.text
    assert 'id="add-to-queue" type="checkbox"' in response.text
    assert "Add to queue" in response.text
    assert 'id="artist-name"' in response.text
    assert "(optional)" in response.text
    assert not re.search(r'<input[^>]*id="artist-name"[^>]*required', response.text)
    assert 'id="infer-metadata-btn"' in response.text
    assert "Infer from filename" in response.text


def test_upload_media_saves_file_and_queues_item(client, tmp_path):
    """Uploaded media should be saved, catalogued, and queued when requested."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        with patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()):
            response = client.post(
                "/api/media/upload",
                data={
                    "title": "Upload Song",
                    "artist": "Upload Artist",
                    "add_to_queue": "true",
                },
                files={"file": ("upload-song.mp4", b"video-bytes", "video/mp4")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["queued"] is True
        assert payload["queue_item_id"] is not None

        saved_file = settings.media_path / payload["filename"]
        assert saved_file.exists()

        with TestingSessionLocal() as db:
            media_item = db.query(MediaItem).filter(MediaItem.id == payload["media_id"]).first()
            assert media_item is not None
            assert media_item.title == "Upload Song"
            assert media_item.artist == "Upload Artist"
            assert media_item.media_path == f"/media/{payload['filename']}"

            queue_item = db.query(QueueItem).filter(QueueItem.id == payload["queue_item_id"]).first()
            assert queue_item is not None
            assert queue_item.media_id == media_item.id
            assert queue_item.requested_karaoke is False
    finally:
        settings.media_path = original_media


def test_upload_media_persists_lyrics_and_queue_karaoke_flag(client, tmp_path):
    """Uploaded lyrics should persist as a sidecar and queued uploads can request karaoke."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        with patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()):
            response = client.post(
                "/api/media/upload",
                data={
                    "title": "Upload Lyrics",
                    "artist": "Upload Artist",
                    "add_to_queue": "true",
                    "is_karaoke": "true",
                    "lyrics_text": "[00:01.00]Uploaded line",
                    "lyrics_format": "lrc",
                },
                files={"file": ("upload-lyrics.mp4", b"video-bytes", "video/mp4")},
            )

        assert response.status_code == 200
        payload = response.json()
        expected_stem = build_media_stem("Upload Lyrics", "Upload Artist")
        assert payload["lyrics_path"] == f"/media/{expected_stem}.lrc"
        assert (settings.media_path / f"{expected_stem}.lrc").read_text(
            encoding="utf-8"
        ) == "[00:01.00]Uploaded line"

        with TestingSessionLocal() as db:
            queue_item = db.query(QueueItem).filter(QueueItem.id == payload["queue_item_id"]).first()
            assert queue_item is not None
            assert queue_item.requested_karaoke is True
            assert queue_item.media.lyrics_path == f"/media/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_upload_media_generates_thumbnail_for_mp3(client, tmp_path):
    """Uploaded MP3 files should trigger thumbnail generation immediately."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        with patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()):
            with patch("routes.media_library.media_thumbnail_service.ensure_thumbnail_for_media_file") as mock_thumb:
                response = client.post(
                    "/api/media/upload",
                    data={
                        "title": "Audio Upload",
                        "artist": "Album Artist",
                        "add_to_queue": "false",
                    },
                    files={"file": ("audio-upload.mp3", b"audio-bytes", "audio/mpeg")},
                )

        assert response.status_code == 200
        payload = response.json()
        mock_thumb.assert_called_once_with(settings.media_path / payload["filename"])
    finally:
        settings.media_path = original_media


@pytest.mark.parametrize(
    "filename",
    ["upload-song.webm", "upload-song.mkv", "upload-song.mov", "upload-song.avi", "upload-song.m4v"],
)
def test_upload_media_supports_common_video_formats(client, tmp_path, filename):
    """Common video uploads should be accepted and catalogued."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        with patch("routes.media_library.manager.broadcast_queue_item_added", new=AsyncMock()):
            response = client.post(
                "/api/media/upload",
                data={
                    "title": "Video Upload",
                    "artist": "",
                    "add_to_queue": "false",
                },
                files={"file": (filename, b"video-bytes", "video/mp4")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["queued"] is False
        saved_file = settings.media_path / payload["filename"]
        assert saved_file.exists()
        assert saved_file.name.endswith(Path(filename).suffix)
    finally:
        settings.media_path = original_media


def test_media_management_page_loads(client):
    """Test media management page renders."""
    response = client.get("/media")
    assert response.status_code == 200
    assert b"Media" in response.content
    assert b"Manage Existing Media" in response.content


def test_media_management_page_uses_database_rows(client):
    """Media management page should render DB-backed library rows and stats."""
    with TestingSessionLocal() as db:
        db.add_all(
            [
                MediaItem(
                    youtube_id="realabc12345",
                    title="Real Song One",
                    artist="Artist One",
                    media_path="/media/real-song-one.mp4",
                    vocals_path="/media/real-song-one.vocals.wav",
                    lyrics_path="/media/real-song-one.lrc",
                    missing=False,
                ),
                MediaItem(
                    youtube_id="realdef67890",
                    title="Real Song Two",
                    artist="Artist Two",
                    media_path="/media/real-song-two.mp4",
                    missing=False,
                ),
                MediaItem(
                    title="Real Song Missing",
                    artist="Artist Missing",
                    media_path="/media/real-song-missing.mp4",
                    lyrics_path="/media/real-song-missing.lrc",
                    missing=True,
                ),
            ]
        )
        db.commit()

    response = client.get("/media")
    assert response.status_code == 200
    content = response.content

    assert b"Real Song One" in content
    assert b"Artist One" in content
    assert b"Real Song Missing" in content
    assert b"https://i.ytimg.com/vi/realabc12345/hqdefault.jpg" in content
    assert b'data-media-path="/media/real-song-one.mp4"' in content

    assert b'data-action="add-to-queue"' in content
    assert b'data-action="edit"' not in content
    assert b'data-action="delete"' not in content
    assert b'data-action="rename"' not in content
    assert b"synced" not in content.lower()
    assert b'id="media-edit-modal"' not in content
    assert b"Missing" in content
    assert b'data-has-multi-track="true"' in content
    assert b'data-has-lyrics="true"' in content
    assert b'data-has-multi-track="false"' in content
    assert b'data-has-lyrics="false"' in content

    assert content.count(b">3</p>") >= 1
    assert content.count(b">1</p>") >= 2
    assert content.count(b">2</p>") >= 1


def test_media_management_page_hides_edit_controls_for_guest(client):
    """Guest media library should be queue-only."""
    with TestingSessionLocal() as db:
        db.add(
            MediaItem(
                title="Admin Delete Song",
                artist="Artist",
                media_path="/media/admin-delete-song.mp4",
                missing=False,
            )
        )
        db.commit()

    response = client.get("/media")

    assert response.status_code == 200
    assert b'data-action="add-to-queue"' in response.content
    assert b'data-action="edit"' not in response.content
    assert b'data-action="delete"' not in response.content
    assert b'data-action="scan-library"' not in response.content
    assert b'data-action="upload-media"' not in response.content


def test_media_management_page_shows_edit_controls_for_admin(client):
    """Admin media library should include edit and delete actions."""
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        db.add(
            MediaItem(
                title="Admin Delete Song",
                artist="Artist",
                media_path="/media/admin-delete-song.mp4",
                missing=False,
            )
        )
        db.commit()

    response = client.get("/media")

    assert response.status_code == 200
    assert b'data-action="edit"' in response.content
    assert b'data-action="delete"' in response.content
    assert b'data-action="scan-library"' in response.content
    assert b'data-action="upload-media"' in response.content


def test_media_scan_route_reconciles_filesystem_and_database(client, tmp_path):
    """Manual media scan route should create and mark rows from filesystem diff."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.media_path / "scan-song.mp4").write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            db.add(
                MediaItem(
                    title="To Missing",
                    media_path="/media/should-be-missing.mp4",
                    missing=False,
                )
            )
            db.commit()

        response = client.post("/api/media/scan")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["summary"]["created"] == 1
        assert payload["summary"]["marked_missing"] == 1

        with TestingSessionLocal() as db:
            created = db.query(MediaItem).filter(MediaItem.media_path == "/media/scan-song.mp4").first()
            assert created is not None
            assert created.title == "scan-song"

            missing_row = db.query(MediaItem).filter(MediaItem.media_path == "/media/should-be-missing.mp4").first()
        assert missing_row is not None
        assert missing_row.missing is True
    finally:
        settings.media_path = original_media


def test_media_scan_route_requires_admin(client):
    """Guest users should not be able to trigger library scans."""
    response = client.post("/api/media/scan")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"


def test_media_scan_single_item_route_refreshes_sidecars(client, tmp_path, monkeypatch):
    """Single-item media scan route should refresh vocals and lyrics sidecars."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "route-single-item.mp4"
        vocals_file = settings.media_path / "route-single-item.vocals.mp3"
        lyrics_file = settings.media_path / "route-single-item.lrc"
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("vocals", encoding="utf-8")
        lyrics_file.write_text("[00:01.00]lyrics", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Route Single Item",
                media_path="/media/route-single-item.mp4",
                missing=True,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        monkeypatch.setattr(
            "routes.media_library.media_library_sync_service.thumbnail_service.ensure_thumbnail_for_media_file",
            lambda path: False,
        )

        response = client.post(f"/api/media/{media_id}/scan")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["summary"]["scanned_files"] == 1
        assert payload["summary"]["restored"] == 1
        assert payload["summary"]["sidecars_updated"] == 1

        with TestingSessionLocal() as db:
            stored = db.query(MediaItem).filter(MediaItem.id == media_id).first()
            assert stored is not None
            assert stored.missing is False
            assert stored.vocals_path == "/media/route-single-item.vocals.mp3"
            assert stored.lyrics_path == "/media/route-single-item.lrc"
            assert stored.last_scanned_at is not None
    finally:
        settings.media_path = original_media


def test_media_delete_route_removes_row_files_and_queue_items(client, tmp_path):
    """Delete route should remove media rows, queue rows, and local files."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "delete-route.mp4"
        vocals_file = settings.media_path / "delete-route.vocals.mp3"
        lyrics_file = settings.cache_path / "lyrics" / "delete-route.lrc"
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("vocals", encoding="utf-8")
        lyrics_file.write_text("[00:01.00]lyrics", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Delete Route",
                artist="Artist",
                media_path="/media/delete-route.mp4",
                vocals_path="/media/delete-route.vocals.mp3",
                lyrics_path="/cache/lyrics/delete-route.lrc",
                missing=False,
            )
            db.add(media)
            db.flush()
            db.add(
                QueueItem(
                    media_id=media.id,
                    position=1000,
                    status=QueueStatus.PENDING,
                )
            )
            db.commit()
            media_id = media.id

        response = client.delete(f"/api/media/{media_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["summary"]["deleted_files"] == 3
        assert payload["summary"]["removed_queue_items"] == 1

        assert not media_file.exists()
        assert not vocals_file.exists()
        assert not lyrics_file.exists()

        with TestingSessionLocal() as db:
            assert db.query(MediaItem).filter(MediaItem.id == media_id).first() is None
            assert db.query(QueueItem).filter(QueueItem.media_id == media_id).count() == 0
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_delete_route_rejects_playing_item(client):
    """Delete route should reject items that are currently playing."""
    authenticate_admin_client(client)
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Playing Route",
            artist="Artist",
            media_path="/media/playing-route.mp4",
            missing=False,
        )
        db.add(media)
        db.flush()
        db.add(
            QueueItem(
                media_id=media.id,
                position=1000,
                status=QueueStatus.PLAYING,
            )
        )
        db.commit()
        media_id = media.id

    response = client.delete(f"/api/media/{media_id}")
    assert response.status_code == 409
    assert "currently playing" in response.json()["detail"].lower()


def test_media_delete_route_requires_admin(client):
    """Guest users should not be able to delete media through the API."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Guest Delete Blocked",
            media_path="/media/guest-delete-blocked.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        media_id = media.id

    response = client.delete(f"/api/media/{media_id}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"


def test_media_rename_route_updates_database_and_files(client, tmp_path):
    """Rename route should update metadata and on-disk assets."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        old_media = settings.media_path / "old-route.mp4"
        old_vocals = settings.media_path / "old-route.vocals.wav"
        old_lyrics = settings.cache_path / "lyrics" / "old-route.lrc"
        old_media.write_text("video", encoding="utf-8")
        old_vocals.write_text("vocals", encoding="utf-8")
        old_lyrics.write_text("[00:01.00]lyrics", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Old Route",
                artist="Old Artist",
                media_path="/media/old-route.mp4",
                vocals_path="/media/old-route.vocals.wav",
                lyrics_path="/cache/lyrics/old-route.lrc",
                missing=False,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        response = client.patch(
            f"/api/media/{media_id}",
            json={
                "title": "New Route",
                "artist": "New Artist",
                "rename_on_disk": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["summary"]["renamed_files"] == 3

        expected_stem = build_media_stem("New Route", "New Artist", fallback="old-route")
        assert not old_media.exists()
        assert not old_vocals.exists()
        assert not old_lyrics.exists()
        assert (settings.media_path / f"{expected_stem}.mp4").exists()
        assert (settings.media_path / f"{expected_stem}.vocals.wav").exists()
        assert (settings.cache_path / "lyrics" / f"{expected_stem}.lrc").exists()

        with TestingSessionLocal() as db:
            stored = db.query(MediaItem).filter(MediaItem.id == media_id).first()
            assert stored is not None
            assert stored.title == "New Route"
            assert stored.artist == "New Artist"
            assert stored.media_path == f"/media/{expected_stem}.mp4"
            assert stored.vocals_path == f"/media/{expected_stem}.vocals.wav"
            assert stored.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_rename_route_requires_admin(client):
    """Guest users should not be able to edit media metadata."""
    with TestingSessionLocal() as db:
        media = MediaItem(
            title="Guest Edit Blocked",
            media_path="/media/guest-edit-blocked.mp4",
            missing=False,
        )
        db.add(media)
        db.commit()
        media_id = media.id

    response = client.patch(
        f"/api/media/{media_id}",
        json={
            "title": "Blocked",
            "artist": None,
            "rename_on_disk": False,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"


def test_media_rename_route_persists_lyrics_text(client, tmp_path):
    """Media edit should be able to save lyrics text as a sidecar."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "editable.mp4"
        media_file.write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Editable",
                artist="Singer",
                file_stem="editable",
                media_path="/media/editable.mp4",
                missing=False,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        response = client.patch(
            f"/api/media/{media_id}",
            json={
                "title": "Editable",
                "artist": "Singer",
                "rename_on_disk": False,
                "lyrics_text": "Plain edited lyrics",
                "lyrics_format": "txt",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["lyrics_path"] == "/media/editable.txt"
        assert (settings.media_path / "editable.txt").read_text(
            encoding="utf-8"
        ) == "Plain edited lyrics"

        with TestingSessionLocal() as db:
            stored = db.query(MediaItem).filter(MediaItem.id == media_id).first()
            assert stored is not None
            assert stored.lyrics_path == "/media/editable.txt"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_scan_preserves_edited_media_adjacent_lyrics(client, tmp_path):
    """Library scan should keep lyrics saved from the edit modal."""
    authenticate_admin_client(client)
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "scan-edit.mp4"
        media_file.write_text("video", encoding="utf-8")

        with TestingSessionLocal() as db:
            media = MediaItem(
                title="Scan Edit",
                artist="Singer",
                file_stem="scan-edit",
                media_path="/media/scan-edit.mp4",
                missing=False,
            )
            db.add(media)
            db.commit()
            media_id = media.id

        response = client.patch(
            f"/api/media/{media_id}",
            json={
                "title": "Scan Edit",
                "artist": "Singer",
                "rename_on_disk": False,
                "lyrics_text": "[00:01.00]Still here",
                "lyrics_format": "lrc",
            },
        )
        assert response.status_code == 200
        assert response.json()["summary"]["lyrics_path"] == "/media/scan-edit.lrc"

        scan_response = client.post("/api/media/scan")
        assert scan_response.status_code == 200

        with TestingSessionLocal() as db:
            stored = db.query(MediaItem).filter(MediaItem.id == media_id).first()
            assert stored is not None
            assert stored.lyrics_path == "/media/scan-edit.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_access_restricted_page_loads(client):
    """Test access restricted page renders."""
    response = client.get("/access-restricted")
    assert response.status_code == 200
    assert b"Access restricted" in response.content


def test_app_startup_triggers_media_scan():
    """Application lifespan should run media library scan on startup."""
    with patch(
        "main.media_library_sync_service.scan_library",
        return_value={
            "scanned_files": 0,
            "created": 0,
            "marked_missing": 0,
            "restored": 0,
            "sidecars_updated": 0,
            "skipped_rows": 0,
        },
    ) as mock_scan:
        with TestClient(app) as startup_client:
            response = startup_client.get("/health")
            assert response.status_code == 200

    assert mock_scan.called


def test_get_runtime_settings(client):
    """Runtime settings endpoint should return current values."""
    authenticate_admin_client(client)
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
    assert "lyrics_provider_netease_enabled" in data
    assert "lyrics_provider_lrclib_enabled" in data
    assert "ffmpeg_path" in data
    assert "media_path" in data
    assert "cache_path" in data
    assert "demucs_healthy" in data
    assert "demucs_health_detail" in data
    assert "stage_qr_url" in data
    assert "stage_lobby_media_path" in data


def test_runtime_settings_api_requires_admin(client):
    """Settings management API should reject guests."""
    response = client.get("/api/settings/")
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"


def test_update_runtime_settings(client):
    """Runtime settings endpoint should apply updates."""
    authenticate_admin_client(client)
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
            "lyrics_provider_netease_enabled": False,
            "lyrics_provider_lrclib_enabled": True,
            "ffmpeg_path": "ffmpeg",
            "stage_qr_url": "https://karaoke.test/queue",
            "stage_lobby_media_path": "/media/stage-lobby.mp4",
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
    assert data["lyrics_provider_netease_enabled"] is False
    assert data["lyrics_provider_lrclib_enabled"] is True
    assert data["stage_qr_url"] == "https://karaoke.test/queue"
    assert data["stage_lobby_media_path"] == "/media/stage-lobby.mp4"
    assert "demucs_healthy" in data
    assert "demucs_health_detail" in data


def test_update_runtime_settings_persists_to_database(client):
    """Runtime settings updates should be written to the database."""
    authenticate_admin_client(client)
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
                "stage_lobby_media_path": "/media/stage-lobby.mp4",
                "concurrent_ytdlp_search_enabled": True,
            },
        )
    assert response.status_code == 200

    db = TestingSessionLocal()
    try:
        stage_qr = db.query(RuntimeSetting).filter(RuntimeSetting.key == "stage_qr_url").first()
        stage_lobby = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "stage_lobby_media_path"
        ).first()
        concurrent = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "concurrent_ytdlp_search_enabled"
        ).first()
        assert stage_qr is not None
        assert stage_qr.value == "https://karaoke.test/queue"
        assert stage_lobby is not None
        assert stage_lobby.value == "/media/stage-lobby.mp4"
        assert concurrent is not None
        assert concurrent.value == "true"
    finally:
        db.close()


def test_get_demucs_health(client):
    """Demucs health endpoint returns current health state."""
    with patch(
        "services.runtime_settings_service.DemucsClient"
    ) as mock_demucs_client:
        mock_instance = Mock()
        mock_instance.health_check.return_value = DemucsHealthResponse(
            api_url="http://localhost:6969",
            healthy=True,
            detail="OK"
        )
        mock_demucs_client.return_value = mock_instance
        
        response = client.get("/api/settings/demucs-health")
        assert response.status_code == 200
        data = response.json()
        assert "api_url" in data
        assert "healthy" in data
        assert "detail" in data


def test_get_ytdlp_version(client):
    """yt-dlp version endpoint should return current version."""
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
    with patch(
        "routes.settings.runtime_settings_service.get_ytdlp_version",
        side_effect=RuntimeError("yt-dlp version check failed"),
    ):
        response = client.get("/api/settings/ytdlp/version")
    assert response.status_code == 400
    assert "yt-dlp version check failed" in response.json()["detail"]


def test_update_ytdlp(client):
    """yt-dlp update endpoint should return update result."""
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
    with patch(
        "routes.settings.runtime_settings_service.update_ytdlp",
        side_effect=RuntimeError("yt-dlp update failed"),
    ):
        response = client.post("/api/settings/ytdlp/update")
    assert response.status_code == 400
    assert "yt-dlp update failed" in response.json()["detail"]


def test_update_runtime_settings_rejects_invalid_crf(client):
    """Runtime settings endpoint should validate ffmpeg_crf."""
    authenticate_admin_client(client)
    response = client.patch("/api/settings/", json={"ffmpeg_crf": 60})
    assert response.status_code == 400
    assert "ffmpeg_crf" in response.json()["detail"]


def test_skip_current_promotes_next_ready(client):
    """Test skip endpoint removes current item and promotes next."""
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
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


def test_guest_cannot_skip_other_guest_current_item(client):
    """Guest users should not be able to skip a current song they did not queue."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-rest-skip-denied", "title": "Guest Rest Skip Denied", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    client.cookies.set("karaoke_guest_id", "guest-other")
    response = client.post("/api/queue/skip")

    assert response.status_code == 403
    assert response.json()["detail"] == "Not allowed to control this stage item"
    with TestingSessionLocal() as db:
        assert db.query(QueueItem).filter(QueueItem.id == first["id"]).first() is not None


def test_guest_can_skip_owned_current_item(client):
    """Guest users may skip their own currently playing song."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-rest-skip-owned", "title": "Guest Rest Skip Owned", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    response = client.post("/api/queue/skip")

    assert response.status_code == 200
    assert response.json() is None
    with TestingSessionLocal() as db:
        assert db.query(QueueItem).filter(QueueItem.id == first["id"]).first() is None


def test_delegated_guest_can_skip_admin_queued_current_item(client):
    """A delegated guest should control the admin-queued current item."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    client.cookies.set("karaoke_queue_tab_id", "tab-admin-device")
    created = client.post(
        "/api/queue/",
        json={
            "youtube_id": "delegated-rest-skip-owned",
            "title": "Delegated REST Skip Owned",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-owner",
        },
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    client.cookies.pop(ADMIN_SESSION_COOKIE, None)
    client.cookies.set("karaoke_guest_id", "guest-owner")
    response = client.post("/api/queue/skip")

    assert response.status_code == 200
    assert response.json() is None


def test_complete_current_requires_admin(client):
    """Guests should not be able to complete the current stage item."""
    response = client.post("/api/queue/complete-current")
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"


def test_complete_current_promotes_next_ready(client):
    """Test complete-current endpoint removes current item and promotes next."""
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
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


def test_move_queue_item_requires_admin(client):
    """Guest users should not be able to reorder queue items."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-move", "title": "Guest Move", "is_karaoke": False},
    ).json()

    response = client.post(
        f"/api/queue/{created['id']}/move",
        json={"direction": "up"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"


def test_move_queue_item_reorders_queue_for_admin(client):
    """Admin reorder requests should update queue positions and ordering."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-move-1", "title": "Admin First", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-move-2", "title": "Admin Second", "is_karaoke": False},
    ).json()
    third = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-move-3", "title": "Admin Third", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        first_row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/queue/{third['id']}/move", json={"direction": "up"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == third["id"]
    assert payload["position"] > first["position"]
    assert payload["position"] < second["position"]

    response = client.get("/api/queue/")
    assert [item["title"] for item in response.json()] == ["Admin First", "Admin Third", "Admin Second"]


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
        assert payload["is_synced"] is True
        assert payload["cues"][0] == {"time": 0.0, "text": "Line one"}
        assert payload["cues"][1] == {"time": 3.0, "text": "Line two"}
        assert payload["lines"] == ["Line one", "Line two"]
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
        assert payload["is_synced"] is True
        assert payload["cues"] == [
            {"time": 1.5, "text": "First"},
            {"time": 4.0, "text": "Fourth"},
        ]
        assert payload["lines"] == ["First", "Fourth"]
    finally:
        if lyrics_file.exists():
            lyrics_file.unlink()


def test_get_queue_item_lyrics_cues_from_txt(client):
    """Lyrics cues endpoint should expose plain text lyrics as unsynced lines."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-txt-1", "title": "Lyric TXT", "is_karaoke": False},
    ).json()

    lyrics_file = Path(settings.media_path) / "route-lyrics.txt"
    lyrics_file.write_text("Line one\n\nLine two\n", encoding="utf-8")

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        assert row is not None
        assert row.media is not None
        row.media.lyrics_path = "/media/route-lyrics.txt"
        db.commit()
    finally:
        db.close()

    try:
        response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_format"] == "txt"
        assert payload["is_synced"] is False
        assert payload["cues"] == []
        assert payload["lines"] == ["Line one", "Line two"]
    finally:
        if lyrics_file.exists():
            lyrics_file.unlink()


def test_transform_chinese_lyrics_endpoint_simplifies_and_pinyinizes(client):
    """Chinese lyrics transform endpoint should simplify Chinese and add optional pinyin."""
    response = client.post(
        "/api/lyrics/chinese-transform",
        json={
            "texts": ["繁體中文", "Hello 世界", "Plain English"],
            "include_pinyin": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0] == {
        "original": "繁體中文",
        "simplified": "繁体中文",
        "pinyin": "fan ti zhong wen",
        "has_chinese": True,
    }
    assert payload["items"][1] == {
        "original": "Hello 世界",
        "simplified": "Hello 世界",
        "pinyin": "Hello shi jie",
        "has_chinese": True,
    }
    assert payload["items"][2] == {
        "original": "Plain English",
        "simplified": "Plain English",
        "pinyin": None,
        "has_chinese": False,
    }


def test_get_queue_item_lyrics_cues_returns_404_without_lyrics(client):
    """Lyrics cues endpoint should return 404 when no lyrics sidecar exists."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-none-1", "title": "Lyric None", "is_karaoke": False},
    ).json()

    response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
    assert response.status_code == 404
    assert "Lyrics not available" in response.json()["detail"]


def test_queue_clear_route_requires_admin(client):
    """Guest users should not be able to clear queue items."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-del", "title": "Guest Delete", "is_karaoke": False},
    ).json()

    clear_response = client.post("/api/queue/clear")

    assert clear_response.status_code == 403
    assert clear_response.json()["detail"] == "Admin session required"


def test_get_queue_marks_can_remove_for_guest_owner(client):
    """Queue list should expose guest removal permissions per item."""
    client.cookies.set("karaoke_guest_id", "guest-123")
    own_item = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-own-api", "title": "Guest Own API", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-999")
    other_item = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-other-api", "title": "Guest Other API", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-123")
    response = client.get("/api/queue/")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    assert items[own_item["id"]]["can_remove"] is True
    assert items[other_item["id"]]["can_remove"] is False


def test_get_queue_marks_delegated_owner_permissions(client):
    """Queue list permissions should follow delegated guest ownership."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    delegated = client.post(
        "/api/queue/",
        json={
            "youtube_id": "delegated-queue-list",
            "title": "Delegated Queue List",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-target",
        },
    ).json()

    client.cookies.pop(ADMIN_SESSION_COOKIE, None)
    client.cookies.set("karaoke_guest_id", "guest-target")
    response = client.get("/api/queue/")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    assert items[delegated["id"]]["can_remove"] is True

    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    response = client.get("/api/queue/")
    items = {item["id"]: item for item in response.json()}
    assert items[delegated["id"]]["can_remove"] is False


def test_get_queue_marks_can_remove_for_admin(client):
    """Admin queue list should allow removal of all non-playing items."""
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-can-remove-1", "title": "Admin First", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "admin-can-remove-2", "title": "Admin Second", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        playing = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        playing.status = QueueStatus.PLAYING
        db.commit()

    authenticate_admin_client(client)
    response = client.get("/api/queue/")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    assert items[first["id"]]["can_remove"] is False
    assert items[second["id"]]["can_remove"] is True


def test_guest_can_remove_owned_queue_item(client):
    """Guest users should be able to remove their own non-playing queue items."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-remove-own", "title": "Guest Remove Own", "is_karaoke": False},
    ).json()

    response = client.delete(f"/api/queue/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"status": "removed", "item_id": created["id"]}


def test_delegated_guest_can_remove_admin_queued_item(client):
    """A delegated guest should remove the admin-queued non-playing item."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    created = client.post(
        "/api/queue/",
        json={
            "youtube_id": "delegated-remove-own",
            "title": "Delegated Remove Own",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-owner",
        },
    ).json()

    client.cookies.pop(ADMIN_SESSION_COOKIE, None)
    client.cookies.set("karaoke_guest_id", "guest-owner")
    response = client.delete(f"/api/queue/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"status": "removed", "item_id": created["id"]}


def test_guest_cannot_remove_other_guest_queue_item(client):
    """Guest users should not be able to remove another guest's queue items."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-remove-other", "title": "Guest Remove Other", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-other")
    response = client.delete(f"/api/queue/{created['id']}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Not allowed to remove this queue item"


def test_guest_cannot_remove_owned_playing_queue_item(client):
    """Guest users should not be able to remove their own currently playing queue item."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-remove-playing", "title": "Guest Remove Playing", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        item = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        item.status = QueueStatus.PLAYING
        db.commit()

    response = client.delete(f"/api/queue/{created['id']}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot remove currently playing item"


def test_get_queue_presence_route_returns_users(client):
    """Presence route should expose the current in-memory roster."""
    from routes.queue import manager

    manager._queue_presence = {
        "guest-1": {
            "display_name": "Alex",
            "joined_at": "2026-05-07T00:00:00",
            "tab_ids": {"tab-1"},
        }
    }
    try:
        response = client.get("/api/queue/presence")
        assert response.status_code == 200
        payload = response.json()
        assert payload["users"][0]["guest_id"] == "guest-1"
        assert payload["users"][0]["display_name"] == "Alex"
        assert payload["users"][0]["connection_count"] == 1
    finally:
        manager._queue_presence.clear()


def test_websocket_connect_and_receive_connected_message(client):
    """WebSocket endpoint should accept connections and send initial connected payload."""
    with client.websocket_connect("/api/queue/ws") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "connected"
        assert "connection_count" in message["data"]
        assert "stage_state" in message["data"]
        assert message["data"]["stage_state"]["lyrics_enabled"] is True
        assert isinstance(message["data"]["stage_state"]["sync_version"], int)


def test_websocket_presence_hello_returns_snapshot(client):
    """Presence hello should register a queue viewer and return a snapshot."""
    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        websocket.send_json(
            {
                "type": "presence_hello",
                "data": {
                    "guest_id": "guest-1",
                    "display_name": "Alex",
                    "tab_id": "tab-1",
                    "page": "queue",
                },
            }
        )

        snapshot = websocket.receive_json()
        assert snapshot["type"] == "presence_snapshot"
        assert snapshot["data"]["users"][0]["display_name"] == "Alex"


def test_websocket_presence_join_update_and_leave(client):
    """Presence lifecycle events should broadcast to other queue viewers."""
    with client.websocket_connect("/api/queue/ws") as first:
        assert first.receive_json()["type"] == "connected"
        first.send_json(
            {
                "type": "presence_hello",
                "data": {
                    "guest_id": "guest-1",
                    "display_name": "Alex",
                    "tab_id": "tab-1",
                    "page": "queue",
                },
            }
        )
        assert first.receive_json()["type"] == "presence_snapshot"

        with client.websocket_connect("/api/queue/ws") as second:
            assert second.receive_json()["type"] == "connected"
            second.send_json(
                {
                    "type": "presence_hello",
                    "data": {
                        "guest_id": "guest-2",
                        "display_name": "Blair",
                        "tab_id": "tab-2",
                        "page": "queue",
                    },
                }
            )
            assert second.receive_json()["type"] == "presence_snapshot"

            joined = first.receive_json()
            while joined["type"] == "ping":
                first.send_json({"type": "pong"})
                joined = first.receive_json()
            assert joined["type"] == "user_joined"
            assert joined["data"]["display_name"] == "Blair"

            second.send_json(
                {
                    "type": "presence_update",
                    "data": {
                        "guest_id": "guest-2",
                        "display_name": "Blair Renamed",
                        "tab_id": "tab-2",
                        "page": "queue",
                    },
                }
            )

            assert second.receive_json()["type"] == "presence_snapshot"
            updated = first.receive_json()
            while updated["type"] == "ping":
                first.send_json({"type": "pong"})
                updated = first.receive_json()
            assert updated["type"] == "user_updated"
            assert updated["data"]["display_name"] == "Blair Renamed"

        left = first.receive_json()
        while left["type"] == "ping":
            first.send_json({"type": "pong"})
            left = first.receive_json()
        assert left["type"] == "user_left"
        assert left["data"]["guest_id"] == "guest-2"


def test_websocket_presence_deduplicates_multiple_tabs(client):
    """Same guest in two tabs should only leave after the final disconnect."""
    with client.websocket_connect("/api/queue/ws") as observer:
        assert observer.receive_json()["type"] == "connected"
        observer.send_json(
            {
                "type": "presence_hello",
                "data": {
                    "guest_id": "observer",
                    "display_name": "Observer",
                    "tab_id": "obs-1",
                    "page": "queue",
                },
            }
        )
        assert observer.receive_json()["type"] == "presence_snapshot"

        with client.websocket_connect("/api/queue/ws") as first_tab:
            assert first_tab.receive_json()["type"] == "connected"
            first_tab.send_json(
                {
                    "type": "presence_hello",
                    "data": {
                        "guest_id": "guest-1",
                        "display_name": "Alex",
                        "tab_id": "tab-1",
                        "page": "queue",
                    },
                }
            )
            assert first_tab.receive_json()["type"] == "presence_snapshot"
            joined = observer.receive_json()
            while joined["type"] == "ping":
                observer.send_json({"type": "pong"})
                joined = observer.receive_json()
            assert joined["type"] == "user_joined"

            with client.websocket_connect("/api/queue/ws") as second_tab:
                assert second_tab.receive_json()["type"] == "connected"
                second_tab.send_json(
                    {
                        "type": "presence_hello",
                        "data": {
                            "guest_id": "guest-1",
                            "display_name": "Alex",
                            "tab_id": "tab-2",
                            "page": "queue",
                        },
                    }
                )
                snapshot = second_tab.receive_json()
                assert snapshot["type"] == "presence_snapshot"
                guest = next(
                    user for user in snapshot["data"]["users"] if user["guest_id"] == "guest-1"
                )
                assert guest["connection_count"] == 2

            response = client.get("/api/queue/presence")
            assert response.status_code == 200
            users = response.json()["users"]
            guest = next(user for user in users if user["guest_id"] == "guest-1")
            assert guest["connection_count"] == 1

        left = observer.receive_json()
        while left["type"] == "ping":
            observer.send_json({"type": "pong"})
            left = observer.receive_json()
        assert left["type"] == "user_left"
        assert left["data"]["guest_id"] == "guest-1"


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
    authenticate_admin_client(client)
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


def test_websocket_broadcasts_queue_item_updated_on_move(client):
    """Reordering a queue item should broadcast queue_item_updated."""
    authenticate_admin_client(client)
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-move-1", "title": "WS Move 1", "is_karaoke": False},
    ).json()
    second = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-move-2", "title": "WS Move 2", "is_karaoke": False},
    ).json()
    third = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-move-3", "title": "WS Move 3", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        first_row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        first_row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    with client.websocket_connect("/api/queue/ws") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        response = client.post(f"/api/queue/{third['id']}/move", json={"direction": "up"})
        assert response.status_code == 200

        event = websocket.receive_json()
        if event["type"] == "ping":
            websocket.send_json({"type": "pong"})
            event = websocket.receive_json()
        assert event["type"] == "queue_item_updated"
        assert event["data"]["id"] == third["id"]
        assert event["data"]["position"] > first["position"]
        assert event["data"]["position"] < second["position"]


def test_websocket_broadcasts_current_item_changed_on_skip(client):
    """Skipping current item should broadcast current_item_changed."""
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
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
            assert state_event["data"]["lyrics_enabled"] is True


def test_websocket_stage_command_set_lyrics_enabled_broadcasts_state(client):
    """Lyrics toggle should broadcast a stage state update."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()

            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "set_lyrics_enabled",
                        "source": "queue",
                        "lyrics_enabled": False,
                    },
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["lyrics_enabled"] is False
            assert state_event["data"]["vocals_enabled"] is True


def test_websocket_guest_cannot_control_other_guest_current_item(client):
    """Guest websocket stage commands should be denied for other guests' songs."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-guest-denied", "title": "WS Guest Denied", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    client.cookies.set("karaoke_guest_id", "guest-other")
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        sender.send_json(
            {
                "type": "stage_command",
                "data": {"command": "pause", "source": "queue"},
                "timestamp": 123,
            }
        )

        response = sender.receive_json()
        if response["type"] == "ping":
            sender.send_json({"type": "pong"})
            response = sender.receive_json()
        assert response["type"] == "error"
        assert response["data"]["detail"] == "Not allowed to control this stage item"


def test_websocket_guest_can_control_owned_current_item(client):
    """Guest websocket stage commands should be allowed for their own current song."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    first = client.post(
        "/api/queue/",
        json={"youtube_id": "ws-guest-owned", "title": "WS Guest Owned", "is_karaoke": False},
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "set_lyrics_enabled",
                        "source": "queue",
                        "lyrics_enabled": False,
                    },
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["lyrics_enabled"] is False


def test_websocket_delegated_guest_can_control_admin_queued_current_item(client):
    """A delegated guest should be authorized for websocket stage commands."""
    authenticate_admin_client(client)
    client.cookies.set("karaoke_guest_id", "guest-admin-device")
    first = client.post(
        "/api/queue/",
        json={
            "youtube_id": "ws-delegated-owned",
            "title": "WS Delegated Owned",
            "is_karaoke": False,
            "queue_as_name": "Taylor",
            "queue_as_guest_id": "guest-owner",
        },
    ).json()

    with TestingSessionLocal() as db:
        row = db.query(QueueItem).filter(QueueItem.id == first["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()

    client.cookies.pop(ADMIN_SESSION_COOKIE, None)
    client.cookies.set("karaoke_guest_id", "guest-owner")
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "set_lyrics_enabled",
                        "source": "queue",
                        "lyrics_enabled": False,
                    },
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["lyrics_enabled"] is False


def test_websocket_stage_command_seek_broadcasts_control_and_state(client):
    """Seek stage command should broadcast target timestamp and paused state."""
    authenticate_admin_client(client)
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
            assert state_event["data"]["current_time"] == 42.5


def test_websocket_stage_time_update_broadcasts_state(client):
    """Stage time updates should refresh the shared playback clock."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()

            sender.send_json(
                {
                    "type": "stage_time_update",
                    "data": {"current_time": 18.25, "is_paused": True, "source": "stage"},
                    "timestamp": 123,
                }
            )

            state_event = receiver.receive_json()
            if state_event["type"] == "ping":
                receiver.send_json({"type": "pong"})
                state_event = receiver.receive_json()
            assert state_event["type"] == "stage_state_update"
            assert state_event["data"]["current_time"] == 18.25
            assert state_event["data"]["is_paused"] is True


def test_websocket_stage_time_update_requires_admin(client):
    """Guest clients should not be able to spoof authoritative stage time."""
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        sender.send_json(
            {
                "type": "stage_time_update",
                "data": {"current_time": 18.25, "is_paused": True, "source": "stage"},
                "timestamp": 123,
            }
        )

        response = sender.receive_json()
        if response["type"] == "ping":
            sender.send_json({"type": "pong"})
            response = sender.receive_json()
        assert response["type"] == "error"
        assert response["data"]["detail"] == "Admin session required for stage time updates"


def test_websocket_stage_command_seek_rejects_invalid_time(client):
    """Invalid seek_time values should return websocket error."""
    authenticate_admin_client(client)
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
    """Resync stage command should broadcast control command with a sync version."""
    authenticate_admin_client(client)
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
            assert isinstance(control_event["data"]["sync_version"], int)


def test_websocket_stage_command_resync_accepts_optional_timeline(client):
    """Resync can carry a concrete timeline when sent by the stage client."""
    authenticate_admin_client(client)
    with client.websocket_connect("/api/queue/ws") as sender:
        sender.receive_json()
        with client.websocket_connect("/api/queue/ws") as receiver:
            receiver.receive_json()
            sender.send_json(
                {
                    "type": "stage_command",
                    "data": {
                        "command": "resync",
                        "source": "stage",
                        "seek_time": 12.75,
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
            assert control_event["data"]["command"] == "resync"
            assert control_event["data"]["source"] == "stage"
            assert control_event["data"]["seek_time"] == 12.75
            assert control_event["data"]["is_paused"] is False
            assert isinstance(control_event["data"]["sync_version"], int)


def test_websocket_stage_command_set_vocals_enabled_broadcasts_state(client):
    """Vocals enabled command should broadcast updated stage mix state."""
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
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
    authenticate_admin_client(client)
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
