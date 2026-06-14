"""Tests for service layer."""
import asyncio
import json
import logging
import threading
import httpx
import pytest
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path
from services.queue_service import QueueService
from services.youtube_service import YouTubeService
from services.karaoke_service import KaraokeService
from services.chinese_lyrics_service import ChineseLyricsService
from services.lyrics_service import LyricsService
from services.demucs_client import DemucsClient
from services.media_naming import build_media_stem
from services.media_library_maintenance_service import (
    MediaItemDeleteConflictError,
    MediaItemNotFoundError,
    MediaItemRenameConflictError,
    MediaLibraryMaintenanceService,
)
from services.processing_task_service import processing_task_service
from services.runtime_settings_service import RuntimeSettingsService
from services.task_stream_service import TaskStreamManager, task_stream_manager
from services.websocket_manager import ConnectionManager
from services.media_library_sync_service import MediaLibrarySyncService
from services.media_library_service import MediaLibraryService
from services.media_thumbnail_service import MediaThumbnailService
from services.stage_lobby_service import StageLobbyService
from services.auth_service import AuthService
from config import EXPLICIT_SETTINGS_FIELDS, settings
from models import (
    AdminUser,
    Base,
    DemucsHealthResponse,
    DemucsResponse,
    MediaItem,
    ProcessingTask,
    ProcessingTaskStatus,
    QueueItem,
    QueueItemCreate,
    RuntimeSetting,
    QueueStatus,
    RuntimeSettingsUpdateRequest,
)
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from database import ensure_auxiliary_schema

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
    ensure_auxiliary_schema(engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def reset_proxy_url_setting():
    """Keep HTTP client tests isolated from proxy-setting mutations in other cases."""
    original_proxy = settings.ytdlp_proxy_url
    settings.ytdlp_proxy_url = ""
    try:
        yield
    finally:
        settings.ytdlp_proxy_url = original_proxy


def test_queue_service_add_to_queue(db_session):
    """Test adding item to queue via service."""
    service = QueueService()
    item = QueueItemCreate(
        youtube_id="test123",
        title="Test Song",
        artist="Test Artist",
        is_karaoke=True,
    )

    result = service.add_to_queue(db_session, item)

    assert result.youtube_id == "test123"
    assert result.title == "Test Song"
    assert result.is_karaoke is True
    assert result.status == QueueStatus.PENDING


def test_queue_service_add_to_queue_includes_thumbnail_for_local_media(db_session, tmp_path, monkeypatch):
    """Queue responses should include cached thumbnails for local media items."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "local-track.mp4"
    media_file.write_bytes(b"media")
    thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(b"thumbnail")

    db_session.add(
        MediaItem(
            youtube_id=None,
            title="Local Thumb",
            artist="Artist",
            media_path="/media/local-track.mp4",
            missing=False,
        )
    )
    db_session.commit()

    service = QueueService()
    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            media_item_id=db_session.query(MediaItem).filter(MediaItem.title == "Local Thumb").first().id,
            title="Local Thumb",
            artist="Artist",
            is_karaoke=False,
        ),
    )

    assert result.thumbnail == MediaThumbnailService.thumbnail_url_for_media_file(media_file)


def test_queue_service_add_to_queue_stores_requester_metadata(db_session):
    """Queue items should preserve requester identity and display name."""
    service = QueueService()

    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="requester123",
            title="Requester Song",
            is_karaoke=False,
        ),
        requester_id="guest-123",
        requester_session_id="tab-123",
        requester_name="Alex",
    )

    stored = db_session.query(QueueItem).filter(QueueItem.id == result.id).first()
    assert stored is not None
    assert stored.user_id == "guest-123"
    assert stored.session_id == "tab-123"
    assert stored.requester_name == "Alex"
    assert result.requested_by_name == "Alex"


def test_queue_service_get_queue_sets_can_remove_for_owner_and_admin(db_session):
    """Queue responses should expose remove permissions for the current viewer."""
    service = QueueService()
    owner_result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="owned-queue-item",
            title="Owned Song",
            is_karaoke=False,
        ),
        requester_id="guest-123",
    )
    other_result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="other-queue-item",
            title="Other Song",
            is_karaoke=False,
        ),
        requester_id="guest-999",
    )

    items_for_owner = service.get_queue(db_session, requester_id="guest-123")
    permission_by_id = {item.id: item.can_remove for item in items_for_owner}

    assert permission_by_id[owner_result.id] is True
    assert permission_by_id[other_result.id] is False
    control_by_id = {item.id: item.can_control_stage for item in items_for_owner}
    assert control_by_id[owner_result.id] is True
    assert control_by_id[other_result.id] is False

    items_for_admin = service.get_queue(db_session, is_admin=True)
    assert all(item.can_remove is True for item in items_for_admin)
    assert all(item.can_control_stage is True for item in items_for_admin)


def test_queue_service_response_includes_step_progress_metadata(db_session):
    """Queue responses should expose the current step metadata for active task progress."""
    service = QueueService()
    created = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="step-progress",
            title="Step Progress",
            is_karaoke=True,
        ),
    )
    task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=created.id,
        target_media_item_id=created.media_id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    asyncio.run(
        processing_task_service.emit_progress(
            task.id,
            queue_item_id=created.id,
            progress_percent=32,
            progress_label="Downloading video",
            progress_label_key="task.downloading_video",
            progress_step_index=1,
            progress_step_total=4,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )
    )

    queue_items = service.get_queue(db_session)
    item = next(entry for entry in queue_items if entry.id == created.id)
    assert item.processing_progress == 32
    assert item.processing_label == "Downloading video"
    assert item.processing_label_key == "task.downloading_video"
    assert item.processing_step_index == 1
    assert item.processing_step_total == 4
    asyncio.run(task_stream_manager.clear_task(task.id))


def test_queue_service_add_to_queue_can_delegate_owner_guest_id(db_session):
    """Queue items may be owned by a delegated guest while showing a delegated label."""
    service = QueueService()

    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="delegated-owner",
            title="Delegated Owner Song",
            is_karaoke=False,
            queue_as_name="Taylor",
            queue_as_guest_id="guest-target",
        ),
        requester_id="guest-admin-device",
        requester_session_id="tab-admin-device",
        requester_name="Taylor",
        owner_guest_id="guest-target",
    )

    stored = db_session.query(QueueItem).filter(QueueItem.id == result.id).first()
    assert stored is not None
    assert stored.user_id == "guest-target"
    assert stored.session_id == "tab-admin-device"
    assert stored.requester_name == "Taylor"
    assert result.requested_by_name == "Taylor"


def test_auth_service_stores_salted_password_hash(db_session):
    """Admin passwords should be stored as salted hashes, not plaintext."""
    service = AuthService()

    admin = service.create_or_update_admin(
        db_session, "Admin", "correct horse battery staple"
    )

    assert admin.username == "admin"
    assert admin.password_hash != "correct horse battery staple"
    assert admin.password_salt
    assert admin.password_iterations >= 600_000
    assert service.authenticate_admin(
        db_session, "ADMIN", "correct horse battery staple"
    ).id == admin.id
    assert service.authenticate_admin(db_session, "admin", "wrong password") is None


def test_auth_service_rotates_salt_when_password_changes(db_session):
    """Password updates should replace the salt and invalidate the old password."""
    service = AuthService()
    first = service.create_or_update_admin(
        db_session, "admin", "correct horse battery staple"
    )
    first_salt = first.password_salt

    updated = service.create_or_update_admin(
        db_session, "ADMIN", "another correct password"
    )

    assert updated.id == first.id
    assert updated.password_salt != first_salt
    assert db_session.query(AdminUser).count() == 1
    assert service.authenticate_admin(
        db_session, "admin", "another correct password"
    )
    assert service.authenticate_admin(
        db_session, "admin", "correct horse battery staple"
    ) is None


def test_auth_service_resolves_and_expires_sessions(db_session):
    """Admin sessions should resolve by token and support explicit deletion."""
    service = AuthService()
    admin = service.create_or_update_admin(
        db_session, "admin", "correct horse battery staple"
    )
    token, _ = service.create_admin_session(db_session, admin)

    assert service.get_admin_for_session(db_session, token).id == admin.id
    service.delete_admin_session(db_session, token)
    assert service.get_admin_for_session(db_session, token) is None


def test_queue_service_updates_youtube_metadata_from_payload(db_session):
    """YouTube-backed media rows should store the submitted title and artist."""
    db_session.add(
        MediaItem(
            youtube_id="resolve123",
            title="Original Video Title",
            artist="Original Uploader",
            media_path="/media/resolve123.mp4",
            missing=False,
        )
    )
    db_session.commit()

    service = QueueService()
    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="resolve123",
            title="Resolved Track Title",
            artist="Resolved Artist",
            is_karaoke=True,
        ),
    )

    stored = (
        db_session.query(MediaItem)
        .filter(MediaItem.youtube_id == "resolve123")
        .first()
    )
    assert stored is not None
    assert stored.title == "Resolved Track Title"
    assert stored.artist == "Resolved Artist"
    assert result.title == "Resolved Track Title"
    assert result.artist == "Resolved Artist"


def test_queue_service_moves_item_up_with_sparse_positions(db_session):
    """Moving an item up should keep sparse ordering stable."""
    service = QueueService()
    first = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-up-1", title="First", is_karaoke=False),
    )
    second = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-up-2", title="Second", is_karaoke=False),
    )
    third = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-up-3", title="Third", is_karaoke=False),
    )
    fourth = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-up-4", title="Fourth", is_karaoke=False),
    )

    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    first_row.status = QueueStatus.PLAYING
    db_session.commit()

    moved = service.move_queue_item(db_session, third.id, "up")
    ordered_titles = [item.title for item in service.get_queue(db_session)]

    assert moved.id == third.id
    assert ordered_titles == ["First", "Third", "Second", "Fourth"]
    assert moved.position < second.position
    assert moved.position > first.position


def test_queue_service_moves_item_down_to_queue_tail(db_session):
    """Moving an item down should append it after the next movable item."""
    service = QueueService()
    first = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-down-1", title="First", is_karaoke=False),
    )
    second = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-down-2", title="Second", is_karaoke=False),
    )
    third = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="move-down-3", title="Third", is_karaoke=False),
    )

    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    first_row.status = QueueStatus.PLAYING
    db_session.commit()

    moved = service.move_queue_item(db_session, second.id, "down")
    ordered_titles = [item.title for item in service.get_queue(db_session)]

    assert moved.id == second.id
    assert ordered_titles == ["First", "Third", "Second"]
    assert moved.position > third.position


def test_queue_service_renumbers_before_reordering_when_gap_is_exhausted(db_session):
    """Dense positions should be renumbered before the move succeeds."""
    service = QueueService()
    first = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="dense-1", title="First", is_karaoke=False),
    )
    second = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="dense-2", title="Second", is_karaoke=False),
    )
    third = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="dense-3", title="Third", is_karaoke=False),
    )
    fourth = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="dense-4", title="Fourth", is_karaoke=False),
    )

    for index, item in enumerate((first, second, third, fourth), start=1):
        row = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
        row.position = 1000 + (index - 1)
    first_row = db_session.query(QueueItem).filter(QueueItem.id == first.id).first()
    first_row.status = QueueStatus.PLAYING
    db_session.commit()

    moved = service.move_queue_item(db_session, third.id, "up")
    refreshed = service.get_queue(db_session)

    assert moved.id == third.id
    assert [item.title for item in refreshed] == ["First", "Third", "Second", "Fourth"]
    assert [item.position for item in refreshed] == [1000, 1500, 2000, 4000]


def test_media_library_sync_service_reconciles_rows_and_sidecars(db_session, tmp_path):
    """Library scan should mark missing rows, create new rows, and refresh sidecars."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        existing_file = settings.media_path / "existing.mp4"
        existing_vocals = settings.media_path / "existing.vocals.mp3"
        existing_lyrics = settings.media_path / "existing.lrc"
        existing_file.write_text("video", encoding="utf-8")
        existing_vocals.write_text("vocals", encoding="utf-8")
        existing_lyrics.write_text("[00:01.00]lyrics", encoding="utf-8")

        new_nested_file = settings.media_path / "nested" / "new-track.mp4"
        new_nested_file.parent.mkdir(parents=True, exist_ok=True)
        new_nested_file.write_text("video", encoding="utf-8")

        db_session.add_all(
            [
                MediaItem(
                    title="Missing Row",
                    media_path="/media/missing.mp4",
                    missing=False,
                ),
                MediaItem(
                    title="Existing Row",
                    media_path="/media/existing.mp4",
                    vocals_path=None,
                    lyrics_path="/media/old-value.lrc",
                    missing=True,
                ),
            ]
        )
        db_session.commit()

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 2
        assert summary["created"] == 1
        assert summary["marked_missing"] == 1
        assert summary["restored"] == 1

        missing_row = db_session.query(MediaItem).filter(MediaItem.media_path == "/media/missing.mp4").first()
        assert missing_row is not None
        assert missing_row.missing is True
        assert missing_row.last_scanned_at is not None

        existing_row = db_session.query(MediaItem).filter(MediaItem.media_path == "/media/existing.mp4").first()
        assert existing_row is not None
        assert existing_row.missing is False
        assert existing_row.vocals_path == "/media/existing.vocals.mp3"
        assert existing_row.lyrics_path == "/media/existing.lrc"

        new_row = db_session.query(MediaItem).filter(MediaItem.media_path == "/media/nested/new-track.mp4").first()
        assert new_row is not None
        assert new_row.title == "new-track"
        assert new_row.artist is None
        assert new_row.file_stem == "new-track"
        assert new_row.missing is False
    finally:
        settings.media_path = original_media


def test_media_library_sync_service_scans_one_item_sidecars(db_session, tmp_path, monkeypatch):
    """Single-item scans should refresh vocals and lyrics sidecar paths."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "single-item.mp4"
        vocals_file = settings.media_path / "single-item.vocals.wav"
        lyrics_file = settings.media_path / "single-item.lrc"
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("vocals", encoding="utf-8")
        lyrics_file.write_text("[00:01.00]lyrics", encoding="utf-8")

        media = MediaItem(
            title="Single Item",
            media_path="/media/single-item.mp4",
            missing=True,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibrarySyncService()
        monkeypatch.setattr(
            service.thumbnail_service,
            "ensure_thumbnail_for_media_file",
            lambda path: False,
        )

        summary = service.scan_media_item(db_session, media.id)

        assert summary["scanned_files"] == 1
        assert summary["restored"] == 1
        assert summary["sidecars_updated"] == 1

        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.missing is False
        assert stored.vocals_path == "/media/single-item.vocals.wav"
        assert stored.lyrics_path == "/media/single-item.lrc"
        assert stored.last_scanned_at is not None
    finally:
        settings.media_path = original_media


def test_media_library_sync_service_detects_json_lyrics_sidecar(db_session, tmp_path, monkeypatch):
    """Single-item scans should treat adjacent JSON lyrics as a valid sidecar."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "json-sidecar.mp4"
        lyrics_file = settings.media_path / "json-sidecar.json"
        media_file.write_text("video", encoding="utf-8")
        lyrics_file.write_text('[{"start":1.0,"text":"Hello"}]', encoding="utf-8")

        media = MediaItem(
            title="JSON Sidecar",
            media_path="/media/json-sidecar.mp4",
            missing=True,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibrarySyncService()
        monkeypatch.setattr(
            service.thumbnail_service,
            "ensure_thumbnail_for_media_file",
            lambda path: False,
        )

        summary = service.scan_media_item(db_session, media.id)

        assert summary["scanned_files"] == 1
        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.lyrics_path == "/media/json-sidecar.json"
    finally:
        settings.media_path = original_media


def test_media_library_sync_service_skips_sidecars_as_primary_media(db_session, tmp_path):
    """Sidecar-only files should not be inserted as standalone media rows."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        (settings.media_path / "track.vocals.mp3").write_text("vocals", encoding="utf-8")
        (settings.media_path / "track.lrc").write_text("[00:00.00]line", encoding="utf-8")

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 0
        assert summary["created"] == 0
        assert db_session.query(MediaItem).count() == 0
    finally:
        settings.media_path = original_media


def test_media_library_sync_service_skips_audio_scratch_files_as_primary_media(
    db_session, tmp_path
):
    """Transient *.audio.* files should not be inserted as standalone media rows."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        (settings.media_path / "track.mp4").write_text("video", encoding="utf-8")
        (settings.media_path / "track.audio.webm").write_text("audio", encoding="utf-8")
        (settings.media_path / "track.vocals.mp3").write_text("vocals", encoding="utf-8")

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        rows = db_session.query(MediaItem).all()
        assert len(rows) == 1
        assert rows[0].media_path == "/media/track.mp4"
        assert rows[0].vocals_path == "/media/track.vocals.mp3"
    finally:
        settings.media_path = original_media


def test_media_library_sync_service_skips_legacy_karaoke_duplicate_when_canonical_exists(
    db_session, tmp_path
):
    """Legacy *.karaoke.mp4 should not become a duplicate row if canonical media exists."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        (settings.media_path / "track.mp4").write_text("video", encoding="utf-8")
        (settings.media_path / "track.karaoke.mp4").write_text("legacy-video", encoding="utf-8")
        (settings.media_path / "track.vocals.mp3").write_text("vocals", encoding="utf-8")

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        rows = db_session.query(MediaItem).all()
        assert len(rows) == 1
        assert rows[0].media_path == "/media/track.mp4"
        assert rows[0].vocals_path == "/media/track.vocals.mp3"
    finally:
        settings.media_path = original_media


def test_media_library_sync_service_keeps_legacy_karaoke_file_when_no_canonical_exists(
    db_session, tmp_path
):
    """Legacy *.karaoke.mp4 remains importable when it is the only playable media file."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        (settings.media_path / "track.karaoke.mp4").write_text("legacy-video", encoding="utf-8")
        (settings.media_path / "track.vocals.mp3").write_text("vocals", encoding="utf-8")

        service = MediaLibrarySyncService()
        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        row = db_session.query(MediaItem).one()
        assert row.media_path == "/media/track.karaoke.mp4"
        assert row.vocals_path == "/media/track.vocals.mp3"
    finally:
        settings.media_path = original_media


def test_media_library_sync_service_generates_thumbnails_for_videos(db_session, tmp_path, monkeypatch):
    """Library scans should request thumbnail generation for local video files."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "scan-me.mp4"
        media_file.write_text("video", encoding="utf-8")

        service = MediaLibrarySyncService()
        calls: list[Path] = []

        def fake_generate(path: Path):
            calls.append(path)
            thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(path)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.write_bytes(b"thumb")
            return thumb_path

        monkeypatch.setattr(service.thumbnail_service, "ensure_thumbnail_for_media_file", fake_generate)

        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        assert summary["thumbnails_updated"] == 1
        assert calls == [media_file]
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_library_sync_service_generates_thumbnails_for_audio_files(db_session, tmp_path, monkeypatch):
    """Library scans should request thumbnail generation for local audio files too."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "scan-me.mp3"
        media_file.write_text("audio", encoding="utf-8")

        service = MediaLibrarySyncService()
        calls: list[Path] = []

        def fake_generate(path: Path):
            calls.append(path)
            thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(path)
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.write_bytes(b"thumb")
            return thumb_path

        monkeypatch.setattr(service.thumbnail_service, "ensure_thumbnail_for_media_file", fake_generate)

        summary = service.scan_library(db_session)

        assert summary["scanned_files"] == 1
        assert summary["created"] == 1
        assert summary["thumbnails_updated"] == 1
        assert calls == [media_file]
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_library_service_uses_cached_local_thumbnail(db_session, tmp_path):
    """Media page rows should use cached thumbnails for local media files."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "local-song.mp4"
        media_file.write_text("video", encoding="utf-8")
        thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"thumb")

        db_session.add(
            MediaItem(
                title="Local Song",
                media_path="/media/local-song.mp4",
                missing=False,
            )
        )
        db_session.commit()

        service = MediaLibraryService()
        items = service.list_media_items(db_session)

        assert len(items) == 1
        assert items[0]["thumbnail"] == MediaThumbnailService.thumbnail_url_for_media_file(media_file)
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_thumbnail_service_uses_embedded_art_extraction_for_audio(tmp_path, monkeypatch):
    """Audio thumbnails should use embedded-art extraction instead of video frame capture."""
    original_cache = settings.cache_path
    try:
        settings.cache_path = tmp_path / "cache"
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        media_file = tmp_path / "album-track.mp3"
        media_file.write_bytes(b"audio")
        service = MediaThumbnailService()
        called: list[str] = []

        def fake_extract_embedded(source_path: Path, output_path: Path):
            called.append(f"embedded:{source_path.name}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"thumb")
            return output_path

        def fail_extract_video(source_path: Path, output_path: Path):
            raise AssertionError("video extraction should not run for audio files")

        monkeypatch.setattr(service.ffmpeg, "extract_embedded_thumbnail", fake_extract_embedded)
        monkeypatch.setattr(service.ffmpeg, "extract_video_thumbnail", fail_extract_video)

        result = service.ensure_thumbnail_for_media_file(media_file)

        assert result == MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        assert called == ["embedded:album-track.mp3"]
    finally:
        settings.cache_path = original_cache


def test_media_library_maintenance_service_deletes_files_and_queue_rows(db_session, tmp_path):
    """Deleting a media item should remove its DB row, queue rows, and local files."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "delete-me.mp4"
        vocals_file = settings.media_path / "delete-me.vocals.wav"
        lyrics_file = settings.cache_path / "lyrics" / "delete-me.lrc"
        thumb_file = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("vocals", encoding="utf-8")
        thumb_file.parent.mkdir(parents=True, exist_ok=True)
        thumb_file.write_bytes(b"thumb")

        media = MediaItem(
            title="Delete Me",
            artist="Singer",
            media_path="/media/delete-me.mp4",
            vocals_path="/media/delete-me.vocals.wav",
            lyrics_path="/cache/lyrics/delete-me.lrc",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()
        db_session.add(
            QueueItem(
                media_id=media.id,
                position=1000,
                status=QueueStatus.PENDING,
            )
        )
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        summary = service.delete_media_item(db_session, media.id)

        assert summary["deleted_files"] == 3
        assert summary["missing_files"] == 1
        assert summary["removed_queue_items"] == 1
        assert not media_file.exists()
        assert not vocals_file.exists()
        assert not lyrics_file.exists()
        assert not thumb_file.exists()
        assert db_session.query(MediaItem).filter(MediaItem.id == media.id).first() is None
        assert db_session.query(QueueItem).filter(QueueItem.media_id == media.id).count() == 0
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_library_maintenance_service_rejects_missing_item(db_session):
    """Deleting a missing media item should raise a not-found error."""
    service = MediaLibraryMaintenanceService()

    with pytest.raises(MediaItemNotFoundError):
        service.delete_media_item(db_session, 9999)


def test_media_library_maintenance_service_rejects_playing_queue_item(db_session):
    """Deleting a currently playing media item should be blocked."""
    media = MediaItem(
        title="Playing Track",
        media_path="/media/playing-track.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.flush()
    db_session.add(
        QueueItem(
            media_id=media.id,
            position=1000,
            status=QueueStatus.PLAYING,
        )
    )
    db_session.commit()

    service = MediaLibraryMaintenanceService()

    with pytest.raises(MediaItemDeleteConflictError):
        service.delete_media_item(db_session, media.id)


def test_media_library_maintenance_service_renames_metadata_and_files(db_session, tmp_path):
    """Renaming a media item should update DB fields and disk assets."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        old_media = settings.media_path / "old-title.mp4"
        old_vocals = settings.media_path / "old-title.vocals.wav"
        old_lyrics = settings.cache_path / "lyrics" / "old-title.lrc"
        old_thumb = MediaThumbnailService.thumbnail_path_for_media_file(old_media)
        old_media.write_text("video", encoding="utf-8")
        old_vocals.write_text("vocals", encoding="utf-8")
        old_lyrics.write_text("[00:01.00]lyrics", encoding="utf-8")
        old_thumb.parent.mkdir(parents=True, exist_ok=True)
        old_thumb.write_bytes(b"thumb")

        media = MediaItem(
            title="Old Title",
            artist="Old Artist",
            media_path="/media/old-title.mp4",
            vocals_path="/media/old-title.vocals.wav",
            lyrics_path="/cache/lyrics/old-title.lrc",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        summary = service.rename_media_item(
            db_session,
            media.id,
            title="New Title",
            artist="New Artist",
            rename_on_disk=True,
        )

        expected_stem = build_media_stem("New Title", "New Artist", fallback=media.youtube_id)
        assert summary["renamed_files"] == 3
        assert summary["target_stem"] == expected_stem
        assert not old_media.exists()
        assert not old_vocals.exists()
        assert not old_lyrics.exists()

        renamed_media = settings.media_path / f"{expected_stem}.mp4"
        renamed_vocals = settings.media_path / f"{expected_stem}.vocals.wav"
        renamed_lyrics = settings.cache_path / "lyrics" / f"{expected_stem}.lrc"
        renamed_thumb = MediaThumbnailService.thumbnail_path_for_media_file(renamed_media)
        assert renamed_media.exists()
        assert renamed_vocals.exists()
        assert renamed_lyrics.exists()
        assert not old_thumb.exists()
        assert renamed_thumb.exists()

        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.title == "New Title"
        assert stored.artist == "New Artist"
        assert stored.file_stem == expected_stem
        assert stored.media_path == f"/media/{expected_stem}.mp4"
        assert stored.vocals_path == f"/media/{expected_stem}.vocals.wav"
        assert stored.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_library_maintenance_service_renames_metadata_without_disk_changes(db_session, tmp_path):
    """Renaming without disk changes should only update database fields."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "unchanged.mp4"
        media_file.write_text("video", encoding="utf-8")

        media = MediaItem(
            title="Unchanged",
            artist="Artist",
            media_path="/media/unchanged.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()
        summary = service.rename_media_item(
            db_session,
            media.id,
            title="Only DB Rename",
            artist="Artist Two",
            rename_on_disk=False,
        )

        assert summary["renamed_files"] == 0
        stored = db_session.query(MediaItem).filter(MediaItem.id == media.id).first()
        assert stored is not None
        assert stored.title == "Only DB Rename"
        assert stored.artist == "Artist Two"
        assert stored.media_path == "/media/unchanged.mp4"
        assert media_file.exists()
    finally:
        settings.media_path = original_media


def test_media_library_maintenance_service_rejects_rename_conflicts(db_session, tmp_path):
    """Renaming should fail when the destination asset already exists."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        conflict_stem = build_media_stem("New Title", "Artist", fallback=None)
        conflict_media = settings.media_path / f"{conflict_stem}.mp4"
        conflict_media.write_text("video", encoding="utf-8")
        old_media = settings.media_path / "old-title.mp4"
        old_media.write_text("video", encoding="utf-8")

        media = MediaItem(
            title="Old Title",
            artist="Artist",
            media_path="/media/old-title.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()

        service = MediaLibraryMaintenanceService()

        with pytest.raises(MediaItemRenameConflictError):
            service.rename_media_item(
                db_session,
                media.id,
                title="New Title",
                artist="Artist",
                rename_on_disk=True,
            )
    finally:
        settings.media_path = original_media


def test_queue_service_renames_existing_media_assets(db_session, tmp_path):
    """Existing media files and sidecars should be renamed to human-readable stems."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        (settings.cache_path / "lyrics").mkdir(parents=True, exist_ok=True)

        old_media = settings.media_path / "abc123.mp4"
        old_vocals = settings.cache_path / "abc123.vocals.mp3"
        old_lyrics = settings.cache_path / "lyrics" / "abc123.lrc"
        old_media.write_text("video", encoding="utf-8")
        old_vocals.write_text("vocals", encoding="utf-8")
        old_lyrics.write_text("[00:01.00]lyrics", encoding="utf-8")

        db_session.add(
            MediaItem(
                youtube_id="abc123",
                title="Old Title",
                artist="Old Artist",
                media_path="/media/abc123.mp4",
                vocals_path="/cache/abc123.vocals.mp3",
                lyrics_path="/cache/lyrics/abc123.lrc",
                missing=False,
            )
        )
        db_session.commit()

        service = QueueService()
        result = service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="abc123",
                title="New Title",
                artist="New Artist",
                is_karaoke=True,
                lyrics_text="[00:01.00]lyrics",
            ),
        )

        expected_stem = build_media_stem("New Title", "New Artist", fallback="abc123")
        stored = (
            db_session.query(MediaItem)
            .filter(MediaItem.youtube_id == "abc123")
            .first()
        )
        assert stored is not None
        assert stored.file_stem == expected_stem
        assert stored.media_path == f"/media/{expected_stem}.mp4"
        assert stored.vocals_path == f"/media/{expected_stem}.vocals.mp3"
        assert stored.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
        assert (settings.media_path / f"{expected_stem}.mp4").exists()
        assert (settings.media_path / f"{expected_stem}.vocals.mp3").exists()
        assert (settings.cache_path / "lyrics" / f"{expected_stem}.lrc").exists()
        assert result.title == "New Title"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


def test_media_items_has_youtube_id_index(db_session):
    """Media item youtube_id lookups should be backed by an index."""
    indexes = inspect(db_session.get_bind()).get_indexes("media_items")
    assert any("youtube_id" in index["name"] for index in indexes)


def test_queue_service_get_queue(db_session):
    """Test getting queue via service."""
    service = QueueService()

    # Add items
    item1 = QueueItemCreate(
        youtube_id="test1", title="Song 1", is_karaoke=False
    )
    item2 = QueueItemCreate(
        youtube_id="test2", title="Song 2", is_karaoke=True
    )
    service.add_to_queue(db_session, item1)
    service.add_to_queue(db_session, item2)

    # Get queue
    queue = service.get_queue(db_session)

    assert len(queue) == 2
    assert queue[0].title == "Song 1"
    assert queue[0].is_karaoke is False
    assert queue[1].title == "Song 2"
    assert queue[1].is_karaoke is True


def test_queue_service_response_includes_vocals_sidecar(db_session):
    """Queue responses should expose existing vocals sidecar paths from media items."""
    media = MediaItem(
        youtube_id="sidecar001",
        title="Sidecar Song",
        artist="Singer",
        media_path="/media/sidecar001.mp4",
        vocals_path="/media/sidecar001.vocals.mp3",
        lyrics_path="/media/sidecar001.lrc",
        missing=False,
    )
    db_session.add(media)
    db_session.flush()

    service = QueueService()
    created = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="sidecar001",
            title="Sidecar Song",
            artist="Singer",
            is_karaoke=False,
        ),
    )

    assert created.vocals_path == "/media/sidecar001.vocals.mp3"
    assert created.lyrics_path == "/media/sidecar001.lrc"


def test_queue_service_persists_lyrics_sidecar_from_queue_payload(db_session, tmp_path):
    """Lyrics text in the queue payload should be written to a reusable sidecar."""
    original_cache = settings.cache_path
    try:
        settings.cache_path = tmp_path / "cache"
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media = MediaItem(
            youtube_id="lyrics001",
            title="Lyrics Song",
            artist="Singer",
            media_path="/media/lyrics001.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        service = QueueService()
        created = service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="lyrics001",
                title="Lyrics Song",
                artist="Singer",
                is_karaoke=True,
                lyrics_text="[00:01.00]Hello lyrics",
            ),
        )

        expected_stem = build_media_stem("Lyrics Song", "Singer", fallback="lyrics001")
        assert created.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
        lyrics_file = settings.cache_path / "lyrics" / f"{expected_stem}.lrc"
        assert lyrics_file.read_text(encoding="utf-8") == "[00:01.00]Hello lyrics"
    finally:
        settings.cache_path = original_cache


def test_queue_service_persists_lyrics_sidecar_for_existing_media(db_session, tmp_path):
    """Lyrics sidecar persistence should be reusable outside queue creation."""
    original_cache = settings.cache_path
    try:
        settings.cache_path = tmp_path / "cache"
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media = MediaItem(
            title="Edited Lyrics",
            artist="Singer",
            file_stem="edited-lyrics",
            media_path="/media/edited-lyrics.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        service = QueueService()
        service.store_lyrics_sidecar(media, "Plain lyrics", lyrics_format="txt")

        assert media.lyrics_path == "/cache/lyrics/edited-lyrics.txt"
        lyrics_file = settings.cache_path / "lyrics" / "edited-lyrics.txt"
        assert lyrics_file.read_text(encoding="utf-8") == "Plain lyrics"
    finally:
        settings.cache_path = original_cache


def test_queue_service_can_persist_media_adjacent_lyrics_sidecar(db_session, tmp_path):
    """Media-library lyrics should be saved next to the media file for scan discovery."""
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        media_file = settings.media_path / "editable.mp4"
        media_file.write_text("video", encoding="utf-8")

        media = MediaItem(
            title="Editable",
            artist="Singer",
            file_stem="editable",
            media_path="/media/editable.mp4",
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        service = QueueService()
        service.store_lyrics_sidecar(
            media,
            "[00:01.00]Media lyrics",
            lyrics_format="lrc",
            storage="media",
        )

        assert media.lyrics_path == "/media/editable.lrc"
        assert (settings.media_path / "editable.lrc").read_text(
            encoding="utf-8"
        ) == "[00:01.00]Media lyrics"
    finally:
        settings.media_path = original_media


def test_queue_service_repairs_swapped_vocals_and_infers_sidecar(db_session, tmp_path):
    """If vocals_path stores lyrics, service should recover lyrics and infer *.vocals sidecar."""
    service = QueueService()
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        expected_stem = build_media_stem("Repair Song", "Singer", fallback="repair001")
        media_file = settings.media_path / "repair-song.mp4"
        vocals_file = settings.media_path / "repair-song.vocals.mp3"
        lyrics_file = settings.media_path / "repair-song.lrc"
        media_file.write_text("video", encoding="utf-8")
        vocals_file.write_text("audio", encoding="utf-8")
        lyrics_file.write_text("[00:00.00]hello", encoding="utf-8")

        media = MediaItem(
            youtube_id="repair001",
            title="Repair Song",
            artist="Singer",
            media_path="/media/repair-song.mp4",
            vocals_path="/media/repair-song.lrc",
            lyrics_path=None,
            missing=False,
        )
        db_session.add(media)
        db_session.flush()

        created = service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="repair001",
                title="Repair Song",
                artist="Singer",
                is_karaoke=False,
            ),
        )

        assert created.vocals_path == f"/media/{expected_stem}.vocals.mp3"
        assert created.lyrics_path == f"/media/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media


def test_queue_service_update_status(db_session):
    """Test updating item status."""
    service = QueueService()
    item = QueueItemCreate(
        youtube_id="test123", title="Test Song", is_karaoke=False
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
    manager._connection_context[socket] = {"role": "queue"}

    with patch("services.websocket_manager.manager", manager):
        await service.update_status_async(db_session, created.id, QueueStatus.READY)

    updated_events = [msg for msg in socket.messages if msg["type"] == "queue_item_updated"]
    assert len(updated_events) == 1
    assert updated_events[0]["data"]["id"] == created.id
    assert updated_events[0]["data"]["status"] == "ready"


@pytest.mark.asyncio
async def test_queue_service_update_status_async_promotes_ready_item_when_idle(db_session):
    """READY status should auto-promote to PLAYING when nothing is currently playing."""
    service = QueueService()
    created = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="auto-promote", title="Auto Promote", is_karaoke=False),
    )
    manager = ConnectionManager()

    class DummySocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    socket = DummySocket()
    manager.active_connections.append(socket)
    manager._connection_context[socket] = {"role": "queue"}

    with patch("services.websocket_manager.manager", manager):
        await service.update_status_async(db_session, created.id, QueueStatus.READY)

    row = db_session.query(QueueItem).filter(QueueItem.id == created.id).first()
    assert row is not None
    assert row.status == QueueStatus.PLAYING
    assert any(
        msg["type"] == "current_item_changed" and msg["data"]["id"] == created.id
        for msg in socket.messages
    )


@pytest.mark.asyncio
async def test_processing_task_emit_progress_broadcasts_queue_item_progress_for_queue_clients(db_session):
    """Queue-backed live task progress should push lightweight queue progress updates."""
    service = QueueService()
    created = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="progress-live", title="Live Progress", is_karaoke=False),
    )
    task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=created.id,
        target_media_item_id=created.media_id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    manager = ConnectionManager()

    class DummySocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    queue_socket = DummySocket()
    stage_socket = DummySocket()
    manager.active_connections.extend([queue_socket, stage_socket])
    manager._connection_context[queue_socket] = {"role": "queue"}
    manager._connection_context[stage_socket] = {"role": "stage"}

    with (
        patch("services.websocket_manager.manager", manager),
    ):
        await processing_task_service.emit_progress(
            task.id,
            queue_item_id=created.id,
            progress_percent=42,
            progress_label="Downloading media",
            progress_label_key="task.downloading_media",
            progress_step_index=1,
            progress_step_total=2,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )

    progress_events = [msg for msg in queue_socket.messages if msg["type"] == "queue_item_progress"]
    assert len(progress_events) == 1
    assert progress_events[0]["data"]["id"] == created.id
    assert progress_events[0]["data"]["task_id"] == task.id
    assert progress_events[0]["data"]["processing_progress"] == 42
    assert progress_events[0]["data"]["processing_label"] == "Downloading media"
    assert progress_events[0]["data"]["processing_label_key"] == "task.downloading_media"
    assert progress_events[0]["data"]["processing_step_index"] == 1
    assert progress_events[0]["data"]["processing_step_total"] == 2
    assert progress_events[0]["data"]["processing_stage"] == "download"
    assert progress_events[0]["data"]["status"] == ProcessingTaskStatus.DOWNLOADING.value
    assert not any(msg["type"] == "queue_item_progress" for msg in stage_socket.messages)
    assert not any(msg["type"] == "queue_item_updated" for msg in queue_socket.messages)

    await task_stream_manager.clear_task(task.id)


@pytest.mark.asyncio
async def test_processing_task_emit_progress_without_queue_item_id_does_not_broadcast_queue_update(db_session):
    """Media-only progress should stay in the task stream and avoid queue websocket fan-out."""
    service = QueueService()
    created = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="progress-media", title="Media Progress", is_karaoke=False),
    )
    task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="uploaded_media",
        target_media_item_id=created.media_id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    manager = ConnectionManager()

    class DummySocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    socket = DummySocket()
    manager.active_connections.append(socket)
    manager._connection_context[socket] = {"role": "queue"}

    with patch("services.websocket_manager.manager", manager):
        await processing_task_service.emit_progress(
            task.id,
            progress_percent=12,
            progress_label="Downloading media",
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )

    assert not any(msg["type"] == "queue_item_progress" for msg in socket.messages)
    assert not any(msg["type"] == "queue_item_updated" for msg in socket.messages)
    await task_stream_manager.clear_task(task.id)


@pytest.mark.asyncio
async def test_demucs_progress_callback_does_not_deadlock_on_same_event_loop():
    """Demucs polling callbacks should not block when already running on the target event loop."""
    loop = asyncio.get_running_loop()
    seen_progress = []
    seen_logs = []

    async def fake_emit_progress(*args, **kwargs):
        seen_progress.append(kwargs)

    async def fake_emit_log(*args, **kwargs):
        seen_logs.append(kwargs)

    with (
        patch("services.karaoke_service.processing_task_service.emit_progress", side_effect=fake_emit_progress),
        patch("services.karaoke_service.processing_task_service.emit_log", side_effect=fake_emit_log),
    ):
        callback = KaraokeService._demucs_progress_callback(
            loop,
            task_id=123,
            step_index=3,
            step_total=4,
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="demucs",
            queue_item_id=456,
        )
        callback(42, "Separating vocals", {"job_id": "job123", "status": "running"})
        await asyncio.sleep(0)

    assert len(seen_progress) == 1
    assert seen_progress[0]["progress_percent"] == 42
    assert len(seen_logs) == 1
    assert seen_logs[0]["message"] == "Demucs job job123: Separating vocals"


@pytest.mark.asyncio
async def test_demucs_progress_callback_switches_to_whisperx_stage_for_alignment():
    """WhisperX alignment should publish its own optimistic stage after Demucs finishes."""
    loop = asyncio.get_running_loop()
    seen_progress = []
    seen_logs = []

    async def fake_emit_progress(*args, **kwargs):
        seen_progress.append(kwargs)

    async def fake_emit_log(*args, **kwargs):
        seen_logs.append(kwargs)

    with (
        patch("services.karaoke_service.processing_task_service.emit_progress", side_effect=fake_emit_progress),
        patch("services.karaoke_service.processing_task_service.emit_log", side_effect=fake_emit_log),
    ):
        callback = KaraokeService._demucs_progress_callback(
            loop,
            task_id=456,
            step_index=3,
            step_total=4,
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="demucs",
            queue_item_id=789,
            has_whisperx=True,
        )
        callback(94, "Separating vocals", {"job_id": "job456", "status": "running"})
        callback(95, "Aligning lyrics", {"job_id": "job456", "status": "running"})
        callback(95, "Aligning lyrics", {"job_id": "job456", "status": "running"})
        callback(100, "Completed", {"job_id": "job456", "status": "completed"})
        await asyncio.sleep(0)

    assert seen_progress[0]["stage"] == "demucs"
    assert seen_progress[0]["progress_percent"] == 94
    assert seen_progress[1]["stage"] == "demucs"
    assert seen_progress[1]["progress_percent"] == 100
    assert seen_progress[2]["stage"] == "whisperx"
    assert seen_progress[2]["progress_percent"] == 0
    assert seen_progress[-1]["stage"] == "whisperx"
    assert seen_progress[-1]["progress_percent"] == 100
    assert any(log["stage"] == "whisperx" for log in seen_logs)
    assert seen_logs[0]["message"] == "Demucs job job456: Separating vocals"


def test_processing_task_cancel_cleans_up_partial_artifacts_and_resets_rows(db_session, tmp_path, monkeypatch):
    """Cancel should remove partial files and reset queue/media rows for retry."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media = MediaItem(
        youtube_id="cancel-me",
        file_stem="cancel-song",
        title="Cancel Song",
        artist="Artist",
        media_path="/media/cancel-song.mp4",
        vocals_path="/media/cancel-song.vocals.wav",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)

    queue_item = QueueItem(
        media_id=media.id,
        position=1,
        requested_karaoke=False,
        user_id="guest-123",
        status=QueueStatus.DOWNLOADING.value,
        error="temporary failure",
    )
    db_session.add(queue_item)
    db_session.commit()
    db_session.refresh(queue_item)

    task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=queue_item.id,
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    media_file = media_root / "cancel-song.mp4"
    vocals_file = media_root / "cancel-song.vocals.wav"
    media_file.write_bytes(b"video")
    vocals_file.write_bytes(b"vocals")
    thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.write_bytes(b"thumbnail")

    for root_name in ("ytdlp", "audio", "processed", "demucs_outputs"):
        artifact_root = cache_root / root_name
        artifact_root.mkdir(parents=True, exist_ok=True)
        (artifact_root / "cancel-song.partial").write_bytes(b"partial")

    asyncio.run(processing_task_service.cancel_task(db_session, task.id))
    asyncio.run(task_stream_manager.clear_task(task.id))

    db_session.refresh(task)
    db_session.refresh(queue_item)
    db_session.refresh(media)

    assert task.status == ProcessingTaskStatus.CANCELED.value
    assert task.last_error_summary is None
    assert task.last_error_detail is None
    assert queue_item.status == QueueStatus.PENDING.value
    assert queue_item.error is None
    assert media.missing is True
    assert media.vocals_path is None
    assert not media_file.exists()
    assert not vocals_file.exists()
    assert not thumbnail_path.exists()
    assert not any((cache_root / "ytdlp").glob("cancel-song*"))
    assert not any((cache_root / "audio").glob("cancel-song*"))
    assert not any((cache_root / "processed").glob("cancel-song*"))
    assert not any((cache_root / "demucs_outputs").glob("cancel-song*"))


def test_media_karaoke_cancel_preserves_original_local_media(db_session, tmp_path, monkeypatch):
    """Canceling a local media task should remove scratch files without deleting the upload."""
    media_root = tmp_path / "media"
    cache_root = tmp_path / "cache"
    media_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setattr(settings, "media_path", media_root)
    monkeypatch.setattr(settings, "cache_path", cache_root)

    media_file = media_root / "local-cancel.mp4"
    media_file.write_bytes(b"original-video")
    media = MediaItem(
        file_stem="local-cancel",
        title="Local Cancel",
        media_path="/media/local-cancel.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="library_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="demucs",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    scratch_root = cache_root / "audio"
    scratch_root.mkdir(parents=True)
    (scratch_root / "local-cancel.audio.m4a").write_bytes(b"scratch")

    asyncio.run(processing_task_service.cancel_task(db_session, task.id))
    asyncio.run(task_stream_manager.clear_task(task.id))

    db_session.refresh(media)
    assert media_file.read_bytes() == b"original-video"
    assert media.missing is False
    assert media.vocals_path is None
    assert not any(scratch_root.glob("local-cancel*"))


def test_processing_task_cancel_permissions_and_cascade_ids(db_session):
    """Guests should only cancel their own active queue tasks while admins get same-media cascades."""
    service = QueueService()
    owner_queue = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="cancel-owner",
            title="Owner Song",
            is_karaoke=False,
        ),
        requester_id="guest-owner",
    )
    other_queue = service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="cancel-other",
            title="Other Song",
            is_karaoke=False,
        ),
        requester_id="guest-other",
    )

    owner_task = processing_task_service.get_or_create_queue_task(db_session, owner_queue.id)
    other_task = processing_task_service.get_or_create_queue_task(db_session, other_queue.id)
    asyncio.run(
        processing_task_service.set_stage(
            db_session,
            owner_task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
        )
    )
    asyncio.run(
        processing_task_service.set_stage(
            db_session,
            other_task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
        )
    )

    assert processing_task_service.can_cancel_task(
        db_session,
        owner_task,
        requester_id="guest-owner",
    ) is True
    assert processing_task_service.can_cancel_task(
        db_session,
        other_task,
        requester_id="guest-owner",
    ) is False

    media = MediaItem(
        youtube_id="cascade-media",
        file_stem="cascade-media",
        title="Cascade Song",
        media_path="/media/cascade-media.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()
    db_session.refresh(media)
    media_queue = QueueItem(
        media_id=media.id,
        position=3,
        requested_karaoke=False,
        status=QueueStatus.DOWNLOADING.value,
    )
    db_session.add(media_queue)
    db_session.commit()
    db_session.refresh(media_queue)
    media_queue_task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=media_queue.id,
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    media_follow_on_task = ProcessingTask(
        task_type="media_karaoke",
        source_kind="library_media",
        target_media_item_id=media.id,
        status=ProcessingTaskStatus.PROCESSING.value,
        stage="demucs",
    )
    db_session.add_all([media_queue_task, media_follow_on_task])
    db_session.commit()
    db_session.refresh(media_queue_task)
    db_session.refresh(media_follow_on_task)

    assert processing_task_service.get_cancelable_task_ids(
        db_session,
        media_queue_task,
        is_admin=True,
    ) == [media_queue_task.id, media_follow_on_task.id]

    asyncio.run(processing_task_service.cancel_task(db_session, media_queue_task.id))
    asyncio.run(processing_task_service.cancel_task(db_session, media_follow_on_task.id))
    asyncio.run(task_stream_manager.clear_task(media_queue_task.id))
    asyncio.run(task_stream_manager.clear_task(media_follow_on_task.id))

    db_session.refresh(media_queue_task)
    db_session.refresh(media_follow_on_task)
    db_session.refresh(media_queue)

    assert media_queue_task.status == ProcessingTaskStatus.CANCELED.value
    assert media_follow_on_task.status == ProcessingTaskStatus.CANCELED.value
    assert media_queue.status == QueueStatus.PENDING.value


def test_karaoke_progress_callback_throttles_to_about_once_per_second():
    """yt-dlp progress callbacks should not emit queue updates every tick."""
    service = KaraokeService()
    emitted = []
    fake_future = Mock()
    fake_future.result.return_value = None

    class FakeLoop:
        def __init__(self):
            self.current_time = 0.0

        def time(self):
            return self.current_time

    loop = FakeLoop()

    with patch("services.karaoke_service.asyncio.run_coroutine_threadsafe") as mock_run:
        def capture(coro, target_loop):
            emitted.append(coro)
            coro.close()
            return fake_future

        mock_run.side_effect = capture
        callback = service._progress_callback(
            loop,
            task_id=123,
            label="Downloading media",
            label_key="task.downloading_media",
            step_index=1,
            step_total=2,
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )

        callback(1, "[download][karaoke-progress] 1.0")
        callback(2, "[download][karaoke-progress] 2.0")
        loop.current_time = 0.5
        callback(3, "[download][karaoke-progress] 3.0")
        loop.current_time = 1.1
        callback(4, "[download][karaoke-progress] 4.0")
        loop.current_time = 1.2
        callback(4, "[download][karaoke-progress] 4.0")
        loop.current_time = 1.3
        callback(100, "[download][karaoke-progress] 100.0")

    assert mock_run.call_count == 3
    assert len(emitted) == 3


@pytest.mark.asyncio
async def test_processing_task_emit_log_does_not_broadcast_queue_item_update(db_session):
    """Log lines should stay in the task stream and not spam queue websocket updates."""
    service = QueueService()
    created = service.add_to_queue(
        db_session,
        QueueItemCreate(youtube_id="log-only", title="Log Only", is_karaoke=False),
    )
    task = ProcessingTask(
        task_type="queue_prepare",
        source_kind="youtube",
        target_queue_item_id=created.id,
        target_media_item_id=created.media_id,
        status=ProcessingTaskStatus.DOWNLOADING.value,
        stage="download",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    manager = ConnectionManager()

    class DummySocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    socket = DummySocket()
    manager.active_connections.append(socket)
    manager._connection_context[socket] = {"role": "queue"}

    with (
        patch("services.websocket_manager.manager", manager),
        patch("services.processing_task_service.SessionLocal", TestingSessionLocal),
    ):
        await processing_task_service.emit_log(
            task.id,
            message="[download][karaoke-progress] 12.0",
            stream="stdout",
            status=ProcessingTaskStatus.DOWNLOADING.value,
            stage="download",
        )

    assert not any(msg["type"] == "queue_item_updated" for msg in socket.messages)
    await task_stream_manager.clear_task(task.id)


@pytest.mark.asyncio
async def test_task_stream_manager_expires_done_tasks_after_ttl(monkeypatch):
    """Completed task live state should drop after the short retention window."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    current_time = {"value": base_time}

    monkeypatch.setattr(
        "services.task_stream_service.utc_now",
        lambda: current_time["value"],
    )

    manager = TaskStreamManager(done_ttl_seconds=60, failed_ttl_seconds=900)
    await manager.ensure_task(101, status="downloading", stage="download")
    await manager.publish(
        101,
        event_type="done",
        status="done",
        stage="ready",
        progress_percent=100,
        progress_label="Ready",
    )
    await manager.mark_task_terminal(101, status="done")

    assert manager.snapshot_now(101) is not None
    assert len(await manager.recent_events(101)) == 1

    current_time["value"] = base_time + timedelta(seconds=61)

    assert manager.snapshot_now(101) is None
    assert await manager.recent_events(101) == []
    assert manager.active_summaries_now() == []


@pytest.mark.asyncio
async def test_task_stream_manager_retains_failed_tasks_longer_than_done(monkeypatch):
    """Failed task logs should remain replayable until the longer failure TTL expires."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    current_time = {"value": base_time}

    monkeypatch.setattr(
        "services.task_stream_service.utc_now",
        lambda: current_time["value"],
    )

    manager = TaskStreamManager(done_ttl_seconds=60, failed_ttl_seconds=900)
    await manager.ensure_task(202, status="processing", stage="demucs")
    await manager.publish(
        202,
        event_type="log",
        status="processing",
        stage="demucs",
        message="separating vocals",
        stream="remote",
    )
    await manager.publish(
        202,
        event_type="error",
        status="failed",
        stage="demucs",
        message="Demucs failed",
        stream="system",
    )
    await manager.mark_task_terminal(202, status="failed")

    current_time["value"] = base_time + timedelta(minutes=10)
    assert manager.snapshot_now(202) is not None
    assert len(await manager.recent_events(202)) == 2

    current_time["value"] = base_time + timedelta(minutes=16)
    assert manager.snapshot_now(202) is None
    assert await manager.recent_events(202) == []


@pytest.mark.asyncio
async def test_connection_manager_presence_registers_and_updates():
    """Presence registration should snapshot, join, update, and leave correctly."""
    manager = ConnectionManager()

    class DummySocket:
        def __init__(self, name):
            self.name = name
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    first = DummySocket("first")
    second = DummySocket("second")

    manager.active_connections.extend([first, second])

    await manager.register_queue_presence(
        first, guest_id="guest-1", display_name="Alex", tab_id="tab-1"
    )
    assert first.messages[-1]["type"] == "presence_snapshot"
    assert first.messages[-1]["data"]["users"][0]["display_name"] == "Alex"

    await manager.register_queue_presence(
        second, guest_id="guest-2", display_name="Blair", tab_id="tab-2"
    )
    assert any(message["type"] == "user_joined" for message in first.messages)
    assert second.messages[-1]["type"] == "presence_snapshot"

    await manager.update_queue_presence(
        second, guest_id="guest-2", display_name="Blair Renamed", tab_id="tab-2"
    )
    assert any(
        message["type"] == "user_updated"
        and message["data"]["display_name"] == "Blair Renamed"
        for message in first.messages
    )

    await manager.disconnect(second)
    assert any(
        message["type"] == "user_left"
        and message["data"]["guest_id"] == "guest-2"
        for message in first.messages
    )


@pytest.mark.asyncio
async def test_connection_manager_presence_deduplicates_tabs_until_last_disconnect():
    """A guest should stay present until their last active tab disconnects."""
    manager = ConnectionManager()

    class DummySocket:
        def __init__(self, name):
            self.name = name
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    observer = DummySocket("observer")
    first_tab = DummySocket("tab1")
    second_tab = DummySocket("tab2")
    manager.active_connections.extend([observer, first_tab, second_tab])

    await manager.register_queue_presence(
        observer, guest_id="observer", display_name="Observer", tab_id="obs-tab"
    )
    await manager.register_queue_presence(
        first_tab, guest_id="guest-1", display_name="Alex", tab_id="tab-1"
    )
    await manager.register_queue_presence(
        second_tab, guest_id="guest-1", display_name="Alex", tab_id="tab-2"
    )

    snapshot = manager.get_queue_presence_snapshot()
    alex = next(user for user in snapshot if user["guest_id"] == "guest-1")
    assert alex["connection_count"] == 2

    await manager.disconnect(first_tab)
    assert not any(
        message["type"] == "user_left" and message["data"]["guest_id"] == "guest-1"
        for message in observer.messages
    )

    await manager.disconnect(second_tab)
    assert any(
        message["type"] == "user_left" and message["data"]["guest_id"] == "guest-1"
        for message in observer.messages
    )


@pytest.mark.asyncio
async def test_connection_manager_stage_time_update_targets_queue_stage_and_lyrics():
    """Playback clock broadcasts should reach queue, stage, and lyrics viewers."""
    manager = ConnectionManager()

    class DummySocket:
        def __init__(self, name):
            self.name = name
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    queue_socket = DummySocket("queue")
    stage_socket = DummySocket("stage")
    lyrics_socket = DummySocket("lyrics")
    manager.active_connections.extend([queue_socket, stage_socket, lyrics_socket])
    manager._connection_context[queue_socket] = {"role": "queue"}
    manager._connection_context[stage_socket] = {"role": "stage"}
    manager._connection_context[lyrics_socket] = {"role": "lyrics_viewer"}

    await manager.set_stage_current_time(12.5, source="stage", is_paused=False)

    assert any(message["type"] == "stage_time_update" for message in queue_socket.messages)
    assert any(message["type"] == "stage_time_update" for message in stage_socket.messages)
    assert any(message["type"] == "stage_time_update" for message in lyrics_socket.messages)


@pytest.mark.asyncio
async def test_connection_manager_reset_stage_state_preserves_mix_preferences():
    """Item transitions should keep the user's vocal and lyrics mix choices."""
    manager = ConnectionManager()
    manager._stage_state["vocals_enabled"] = False
    manager._stage_state["vocals_volume"] = 0.35
    manager._stage_state["lyrics_enabled"] = False
    manager._stage_state["is_paused"] = True
    manager._stage_state["current_time"] = 91.5

    class DummySocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    socket = DummySocket()
    manager.active_connections.append(socket)
    manager._connection_context[socket] = {"role": "queue"}

    await manager.reset_stage_state(source="queue")

    state = manager.get_stage_state()
    assert state["vocals_enabled"] is False
    assert state["vocals_volume"] == 0.35
    assert state["lyrics_enabled"] is False
    assert state["is_paused"] is False
    assert state["current_time"] == 0.0
    assert socket.messages[-1]["type"] == "stage_state_update"
    assert socket.messages[-1]["data"]["vocals_enabled"] is False
    assert socket.messages[-1]["data"]["vocals_volume"] == 0.35
    assert socket.messages[-1]["data"]["lyrics_enabled"] is False


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
def test_youtube_service_search_marks_downloaded_results(mock_ytdlp, db_session):
    """Search results should be flagged when the video already exists locally."""
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "saved123",
            "title": "Already Saved",
            "channel": "Library",
            "duration": "2:00",
            "thumbnail": None,
        }
    ]
    mock_ytdlp.return_value = mock_instance
    db_session.add(
        MediaItem(
            youtube_id="saved123",
            title="Already Saved",
            artist="Library",
            media_path="/media/saved123.mp4",
            missing=False,
        )
    )
    db_session.commit()

    service = YouTubeService()
    results = service.search("totally-unrelated-query", db=db_session)

    assert len(results) == 1
    assert results[0].downloaded is True
    assert results[0].thumbnail == "https://i.ytimg.com/vi/saved123/hqdefault.jpg"
    assert results[0].source == "youtube"


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_prefers_local_and_hides_youtube_duplicates(
    mock_ytdlp, db_session
):
    """Local DB matches should be ordered first and suppress duplicate YouTube hits."""
    local_media = MediaItem(
        youtube_id="dup123",
        title="Bohemian Rhapsody",
        artist="Queen",
        media_path="/media/dup123.mp4",
        missing=False,
    )
    db_session.add(local_media)
    db_session.commit()

    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "dup123",
            "title": "Bohemian Rhapsody",
            "channel": "Queen Official",
            "duration": "5:55",
            "thumbnail": None,
        },
        {
            "video_id": "yt999",
            "title": "Another Song",
            "channel": "Other Channel",
            "duration": "3:00",
            "thumbnail": None,
        },
    ]
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("bohemian queen", db=db_session)

    assert len(results) == 2
    assert results[0].source == "local"
    assert results[0].media_item_id == local_media.id
    assert results[0].video_id == "dup123"
    assert results[1].source == "youtube"
    assert results[1].video_id == "yt999"


@patch("services.youtube_service.YtDlpAdapter")
def test_youtube_service_search_returns_local_items_without_youtube_id(
    mock_ytdlp, db_session
):
    """Local results should still be searchable/queueable when youtube_id is null."""
    db_session.add(
        MediaItem(
            youtube_id=None,
            title="Custom Local Track",
            artist="Home Rip",
            media_path="/media/custom-local-track.mp4",
            missing=False,
        )
    )
    db_session.commit()

    mock_instance = Mock()
    mock_instance.search.return_value = []
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("custom local", db=db_session)

    assert len(results) == 1
    assert results[0].source == "local"
    assert results[0].media_item_id is not None
    assert results[0].video_id is None


def test_queue_service_add_to_queue_by_media_item_id(db_session):
    """Queue service should support enqueue by existing media_item id."""
    media = MediaItem(
        youtube_id="existing123",
        title="Existing Local",
        artist="Artist",
        media_path="/media/existing123.mp4",
        missing=False,
    )
    db_session.add(media)
    db_session.commit()

    service = QueueService()
    result = service.add_to_queue(
        db_session,
        QueueItemCreate(
            media_item_id=media.id,
            title="Existing Local",
            artist="Artist",
            is_karaoke=False,
        ),
    )

    assert result.media_id == media.id
    assert result.youtube_id == "existing123"


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
async def test_karaoke_service_non_karaoke_uses_progressive_download(db_session, tmp_path):
    """Non-karaoke processing should use video+audio direct download."""
    queue_service = QueueService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        downloaded_file = settings.cache_path / "plain123.mp4"
        downloaded_file.write_text("video", encoding="utf-8")

        item = queue_service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="plain123",
                title="Plain Song",
                is_karaoke=False,
            ),
        )

        service = KaraokeService()
        service.youtube_service = Mock()
        service.queue_service = queue_service
        service.youtube_service.download_video_with_audio.return_value = downloaded_file

        await service.process_queue_item(db_session, item.id)

        service.youtube_service.download_video_with_audio.assert_called_once_with(
            "plain123",
            settings.cache_path / "ytdlp",
        )
        service.youtube_service.download_video.assert_not_called()
        service.youtube_service.download_audio.assert_not_called()

        updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
        assert updated_item is not None
        assert updated_item.status == QueueStatus.PLAYING
        assert updated_item.media is not None
        expected_stem = build_media_stem("Plain Song", None, fallback="plain123")
        assert updated_item.media.media_path == f"/media/{expected_stem}.mp4"
        assert (settings.media_path / f"{expected_stem}.mp4").exists()
        assert not downloaded_file.exists()
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


@pytest.mark.asyncio
async def test_karaoke_service_uses_existing_lyrics_sidecar_without_resolution(db_session, tmp_path):
    """Karaoke processing should preserve an existing saved lyrics sidecar."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        expected_stem = build_media_stem("Karaoke Ready", "Singer", fallback="karaoke-ready")
        media_file = settings.media_path / f"{expected_stem}.mp4"
        lyrics_file = settings.cache_path / "lyrics" / f"{expected_stem}.lrc"
        lyrics_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_text("video", encoding="utf-8")
        lyrics_file.write_text("[00:01.00]Existing lyrics", encoding="utf-8")
        db_session.add(
            MediaItem(
                youtube_id="karaoke-ready",
                title="Karaoke Ready",
                artist="Singer",
                file_stem=expected_stem,
                media_path=f"/media/{expected_stem}.mp4",
                lyrics_path=f"/cache/lyrics/{expected_stem}.lrc",
                missing=False,
            )
        )
        db_session.flush()

        queue_service = QueueService()
        item = queue_service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="karaoke-ready",
                title="Karaoke Ready",
                artist="Singer",
                is_karaoke=True,
                lyrics_text="[00:01.00]Existing lyrics",
            ),
        )

        service = KaraokeService()
        service.youtube_service = Mock()
        service.queue_service = queue_service
        service.demucs_client = Mock()
        service.ffmpeg = Mock()

        service.demucs_client.health_check.return_value = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=True,
            detail="ok",
        )
        service.ffmpeg.extract_audio.return_value = settings.cache_path / "audio" / f"{expected_stem}.audio.wav"
        no_vocals_path = settings.cache_path / "stem" / f"{expected_stem}.no_vocals.wav"
        vocals_path = settings.cache_path / "stem" / f"{expected_stem}.vocals.wav"
        no_vocals_path.parent.mkdir(parents=True, exist_ok=True)
        no_vocals_path.write_text("no vocals", encoding="utf-8")
        vocals_path.write_text("vocals", encoding="utf-8")
        def fake_combine_audio_video(*, video_path, audio_path, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("karaoke video", encoding="utf-8")
        service.demucs_client.separate_vocals = AsyncMock(
            return_value=DemucsResponse(
                no_vocals_path=str(no_vocals_path),
                vocals_path=str(vocals_path),
            )
        )
        service.ffmpeg.combine_audio_video.side_effect = fake_combine_audio_video
        await service.process_queue_item(db_session, item.id)

        updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
        assert updated_item is not None
        assert updated_item.status == QueueStatus.PLAYING
        assert updated_item.media is not None
        assert updated_item.media.lyrics_path == f"/cache/lyrics/{expected_stem}.lrc"
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


@pytest.mark.asyncio
async def test_karaoke_service_promotes_aligned_json_sidecar_for_display(db_session, tmp_path):
    """Karaoke processing should prefer the returned aligned JSON sidecar for playback lyrics."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        expected_stem = build_media_stem("Karaoke Ready", "Singer", fallback="karaoke-ready")
        media_file = settings.media_path / f"{expected_stem}.mp4"
        lyrics_file = settings.cache_path / "lyrics" / f"{expected_stem}.lrc"
        aligned_file = settings.cache_path / "demucs_outputs" / f"{expected_stem}.aligned.json"
        lyrics_file.parent.mkdir(parents=True, exist_ok=True)
        aligned_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_text("video", encoding="utf-8")
        lyrics_file.write_text("[00:01.00]Existing lyrics", encoding="utf-8")
        aligned_file.write_text(
            '[{"start": 1.0, "end": 2.0, "text": "Existing lyrics", "words": [{"word": "Existing", "start": 1.0, "end": 1.5}, {"word": "lyrics", "start": 1.5, "end": 2.0}]}]',
            encoding="utf-8",
        )
        db_session.add(
            MediaItem(
                youtube_id="karaoke-ready",
                title="Karaoke Ready",
                artist="Singer",
                file_stem=expected_stem,
                media_path=f"/media/{expected_stem}.mp4",
                lyrics_path=f"/cache/lyrics/{expected_stem}.lrc",
                missing=False,
            )
        )
        db_session.flush()

        queue_service = QueueService()
        item = queue_service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="karaoke-ready",
                title="Karaoke Ready",
                artist="Singer",
                is_karaoke=True,
                lyrics_text="[00:01.00]Existing lyrics",
            ),
        )

        service = KaraokeService()
        service.youtube_service = Mock()
        service.queue_service = queue_service
        service.demucs_client = Mock()
        service.ffmpeg = Mock()

        service.demucs_client.health_check.return_value = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=True,
            detail="ok",
        )
        service.ffmpeg.extract_audio.return_value = settings.cache_path / "audio" / f"{expected_stem}.audio.wav"
        no_vocals_path = settings.cache_path / "stem" / f"{expected_stem}.no_vocals.wav"
        vocals_path = settings.cache_path / "stem" / f"{expected_stem}.vocals.wav"
        no_vocals_path.parent.mkdir(parents=True, exist_ok=True)
        no_vocals_path.write_text("no vocals", encoding="utf-8")
        vocals_path.write_text("vocals", encoding="utf-8")

        def fake_combine_audio_video(*, video_path, audio_path, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("karaoke video", encoding="utf-8")

        service.demucs_client.separate_vocals = AsyncMock(
            return_value=DemucsResponse(
                no_vocals_path=str(no_vocals_path),
                vocals_path=str(vocals_path),
                aligned_lyrics_path=str(aligned_file),
            )
        )
        service.ffmpeg.combine_audio_video.side_effect = fake_combine_audio_video

        await service.process_queue_item(db_session, item.id)

        updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
        assert updated_item is not None
        assert updated_item.status == QueueStatus.PLAYING
        assert updated_item.media is not None
        assert updated_item.media.lyrics_path == f"/media/{expected_stem}.json"
        assert (settings.media_path / f"{expected_stem}.json").read_text(encoding="utf-8") == aligned_file.read_text(
            encoding="utf-8"
        )
        assert lyrics_file.exists()
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


@pytest.mark.asyncio
async def test_lyrics_service_fetch():
    """Lyrics service should prefer syncedLyrics from LRCLIB results."""
    from services import lyrics_service as ls_module

    service = LyricsService(
        metadata_inferrer=ls_module.YouTubeTitleInferrer(lastfm_api_key=""),
        providers=[ls_module.LRCLibLyricsProvider()],
    )

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

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        lyrics = await service.fetch_lyrics("Test Song", "Test Artist")
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert lyrics == "[00:01.00]Synced line"


@pytest.mark.asyncio
async def test_lyrics_service_infers_artist_and_title_from_youtube_title():
    """Metadata inferrer should split cleaned YouTube-style titles."""
    from services import lyrics_service as ls_module

    service = LyricsService(
        metadata_inferrer=ls_module.YouTubeTitleInferrer(lastfm_api_key=""),
        providers=[ls_module.LRCLibLyricsProvider()],
    )

    inferred = await service.infer_song_metadata(
        title="Taylor Swift - Enchanted (Taylor's Version) (Lyric Video)",
        artist=None,
    )

    assert inferred.artist == "Taylor Swift"
    assert inferred.title == "Enchanted (Taylor's Version)"
    assert inferred.source == "regex"


@pytest.mark.asyncio
async def test_lyrics_service_prefers_lastfm_when_configured():
    """Inferrer should use Last.fm match scoring when an API key is configured."""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": {
                    "trackmatches": {
                        "track": [
                            {"name": "Wrong Song (Live)", "artist": "Random Artist"},
                            {"name": "Enchanted", "artist": "Taylor Swift", "mbid": "x"},
                        ]
                    }
                }
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            assert "audioscrobbler" in url
            assert params["method"] == "track.search"
            return FakeResponse()

    from services import lyrics_service as ls_module

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        service = LyricsService(
            metadata_inferrer=ls_module.YouTubeTitleInferrer(lastfm_api_key="test-key")
        )
        inferred = await service.infer_song_metadata(
            title="Taylor Swift - Enchanted (Taylor's Version) (Lyric Video)",
            artist=None,
        )
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert inferred.artist == "Taylor Swift"
    assert inferred.title == "Enchanted"
    assert inferred.source == "lastfm"


@pytest.mark.asyncio
async def test_lyrics_service_lastfm_uses_runtime_proxy_when_configured():
    """Last.fm metadata lookup should use the runtime proxy URL when configured."""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": {
                    "trackmatches": {
                        "track": [{"name": "Enchanted", "artist": "Taylor Swift"}]
                    }
                }
            }

    observed = {"proxy": None, "timeout": None}

    class FakeAsyncClient:
        def __init__(self, timeout, proxy=None):
            observed["timeout"] = timeout
            observed["proxy"] = proxy

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            return FakeResponse()

    from services import lyrics_service as ls_module

    original_proxy = settings.ytdlp_proxy_url
    original_client = ls_module.httpx.AsyncClient
    try:
        settings.ytdlp_proxy_url = "socks5://127.0.0.1:1080"
        ls_module.httpx.AsyncClient = FakeAsyncClient
        service = LyricsService(
            metadata_inferrer=ls_module.YouTubeTitleInferrer(lastfm_api_key="test-key")
        )
        inferred = await service.infer_song_metadata(
            title="Taylor Swift - Enchanted (Taylor's Version) (Lyric Video)",
            artist=None,
        )
    finally:
        ls_module.httpx.AsyncClient = original_client
        settings.ytdlp_proxy_url = original_proxy

    assert inferred.source == "lastfm"
    assert observed["timeout"] == 5.0
    assert observed["proxy"] == "socks5://127.0.0.1:1080"


@pytest.mark.asyncio
async def test_lyrics_service_strips_artist_prefix_from_lastfm_track_name():
    """Last.fm track names that already include the artist should not duplicate it."""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": {
                    "trackmatches": {
                        "track": [
                            {
                                "name": "Miley Cyrus - Party in the U.S.A.",
                                "artist": "Miley Cyrus",
                            }
                        ]
                    }
                }
            }

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
        service = LyricsService(
            metadata_inferrer=ls_module.YouTubeTitleInferrer(lastfm_api_key="test-key")
        )
        inferred = await service.infer_song_metadata(
            title="Miley Cyrus - Party In The U.S.A (Lyrics)",
            artist=None,
        )
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert inferred.title == "Party in the U.S.A."
    assert inferred.artist == "Miley Cyrus"
    assert inferred.source == "lastfm"


@pytest.mark.asyncio
async def test_lyrics_service_fetch_uses_inferred_metadata_query():
    """Fetch should derive artist/title from title-only input before provider lookup."""
    from services import lyrics_service as ls_module

    service = LyricsService(
        metadata_inferrer=ls_module.YouTubeTitleInferrer(lastfm_api_key=""),
        providers=[ls_module.LRCLibLyricsProvider()],
    )
    observed_queries = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "trackName": "Enchanted",
                    "artistName": "Taylor Swift",
                    "syncedLyrics": "[00:01.00]Inferred line",
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
            observed_queries.append(params.get("q"))
            return FakeResponse()

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        lyrics = await service.fetch_lyrics("Taylor Swift - Enchanted (Lyric Video)")
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert lyrics == "[00:01.00]Inferred line"
    assert observed_queries
    assert observed_queries[0] == "Enchanted Taylor Swift"


@pytest.mark.asyncio
async def test_lyrics_service_fetch_falls_back_to_plain():
    """Lyrics service should fall back to plain lyrics when synced lyrics is missing."""
    from services import lyrics_service as ls_module

    service = LyricsService(providers=[ls_module.LRCLibLyricsProvider()])

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

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        lyrics = await service.fetch_lyrics("Another Song", "Another Artist")
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert lyrics == "Plain only line"


@pytest.mark.asyncio
async def test_lyrics_provider_uses_runtime_proxy_when_configured():
    """Lyrics provider HTTP requests should use runtime proxy settings."""
    from services import lyrics_service as ls_module

    observed = {"proxy": None, "timeout": None}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "trackName": "Test Song",
                    "artistName": "Test Artist",
                    "syncedLyrics": "[00:01.00]Synced line",
                }
            ]

    class FakeAsyncClient:
        def __init__(self, timeout, proxy=None):
            observed["timeout"] = timeout
            observed["proxy"] = proxy

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            return FakeResponse()

    original_proxy = settings.ytdlp_proxy_url
    original_client = ls_module.httpx.AsyncClient
    try:
        settings.ytdlp_proxy_url = "http://127.0.0.1:8080"
        ls_module.httpx.AsyncClient = FakeAsyncClient
        service = LyricsService(
            metadata_inferrer=ls_module.YouTubeTitleInferrer(lastfm_api_key=""),
            providers=[ls_module.LRCLibLyricsProvider()],
        )
        lyrics = await service.fetch_lyrics("Test Song", "Test Artist")
    finally:
        ls_module.httpx.AsyncClient = original_client
        settings.ytdlp_proxy_url = original_proxy

    assert lyrics == "[00:01.00]Synced line"
    assert observed["timeout"] == 10.0
    assert observed["proxy"] == "http://127.0.0.1:8080"


@pytest.mark.asyncio
async def test_musixmatch_provider_prefers_synced_lrc_payload():
    """Musixmatch provider should convert subtitle timeline payload into LRC lines."""
    from services import lyrics_service as ls_module

    provider = ls_module.MusixmatchLyricsProvider(token="token123")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "header": {"status_code": 200},
                    "body": {
                        "macro_calls": {
                            "matcher.track.get": {
                                "message": {
                                    "header": {"status_code": 200},
                                    "body": {
                                        "track": {
                                            "track_name": "Resolved Song",
                                            "artist_name": "Resolved Artist",
                                            "instrumental": 0,
                                        }
                                    },
                                }
                            },
                            "track.subtitles.get": {
                                "message": {
                                    "body": {
                                        "subtitle_list": [
                                            {
                                                "subtitle": {
                                                    "subtitle_body": '[{"text":"Line A","time":{"minutes":0,"seconds":1,"hundredths":20}}]'
                                                }
                                            }
                                        ]
                                    }
                                }
                            },
                            "track.lyrics.get": {
                                "message": {"body": {"lyrics": {"lyrics_body": "Fallback plain"}}}
                            },
                        }
                    },
                }
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params, headers):
            assert "macro.subtitles.get" in url
            assert params["q_track"] == "Input Song"
            assert params["usertoken"] == "token123"
            assert "cookie" in headers
            return FakeResponse()

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        payload = await provider.fetch(
            ls_module.InferredSong(title="Input Song", artist="Input Artist", source="regex")
        )
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert payload is not None
    assert payload.provider == "musixmatch"
    assert payload.is_synced is True
    assert payload.lyrics == "[00:01.20]Line A"
    assert payload.inferred_song.title == "Resolved Song"
    assert payload.inferred_song.artist == "Resolved Artist"


@pytest.mark.asyncio
async def test_musixmatch_provider_falls_back_to_plain_and_strips_disclaimer():
    """Musixmatch provider should return plain lyrics when synced payload is missing."""
    from services import lyrics_service as ls_module

    provider = ls_module.MusixmatchLyricsProvider(token="token123")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "header": {"status_code": 200},
                    "body": {
                        "macro_calls": {
                            "matcher.track.get": {
                                "message": {
                                    "header": {"status_code": 200},
                                    "body": {"track": {"instrumental": 0}},
                                }
                            },
                            "track.subtitles.get": {
                                "message": {"body": {"subtitle_list": []}}
                            },
                            "track.lyrics.get": {
                                "message": {
                                    "body": {
                                        "lyrics": {
                                            "restricted": 0,
                                            "lyrics_body": (
                                                "Line 1\n"
                                                "Line 2\n"
                                                "******* This Lyrics is NOT for Commercial use *******"
                                            ),
                                        }
                                    }
                                }
                            },
                        }
                    },
                }
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params, headers):
            return FakeResponse()

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        payload = await provider.fetch(
            ls_module.InferredSong(title="Input Song", artist="Input Artist", source="regex")
        )
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert payload is not None
    assert payload.is_synced is False
    assert payload.lyrics == "Line 1\nLine 2"


@pytest.mark.asyncio
async def test_musixmatch_provider_returns_none_for_auth_or_match_failures():
    """Musixmatch provider should fail gracefully on non-success matcher statuses."""
    from services import lyrics_service as ls_module

    provider = ls_module.MusixmatchLyricsProvider(token="token123")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "header": {"status_code": 200},
                    "body": {
                        "macro_calls": {
                            "matcher.track.get": {"message": {"header": {"status_code": 401}}}
                        }
                    },
                }
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params, headers):
            return FakeResponse()

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        payload = await provider.fetch(
            ls_module.InferredSong(title="Input Song", artist="Input Artist", source="regex")
        )
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert payload is None


@pytest.mark.asyncio
async def test_lyrics_service_provider_fallback_uses_lrclib_after_musixmatch_miss():
    """Orchestrator should continue to fallback providers when Musixmatch yields no payload."""
    from services import lyrics_service as ls_module

    inferred = ls_module.InferredSong(title="Song", artist="Artist", source="regex")

    class FakeInferrer:
        async def infer(self, title: str, artist: str | None = None):
            return inferred

    class FakeMusixProvider:
        name = "musixmatch"

        def __init__(self):
            self.calls = 0

        async def fetch(self, inferred_song):
            self.calls += 1
            return None

    class FakeLrclibProvider:
        name = "lrclib"

        def __init__(self):
            self.calls = 0

        async def fetch(self, inferred_song):
            self.calls += 1
            return ls_module.LyricsPayload(
                lyrics="[00:01.00]Fallback line",
                is_synced=True,
                provider="lrclib",
                inferred_song=inferred_song,
            )

    musix = FakeMusixProvider()
    lrclib = FakeLrclibProvider()
    service = LyricsService(metadata_inferrer=FakeInferrer(), providers=[musix, lrclib])

    payload = await service.resolve_lyrics(title="Song", artist="Artist")

    assert payload is not None
    assert payload.provider == "lrclib"
    assert musix.calls == 1
    assert lrclib.calls == 1


@pytest.mark.asyncio
async def test_lyrics_service_debug_logs_search_and_not_found(caplog):
    """Debug logs should describe the title inference and provider lookup."""
    from services import lyrics_service as ls_module

    inferred = ls_module.InferredSong(title="Clean Song", artist="Clean Artist", source="regex")

    class FakeInferrer:
        async def infer(self, title: str, artist: str | None = None):
            return inferred

    class FakeProvider:
        name = "lrclib"

        async def fetch(self, inferred_song):
            return None

    service = LyricsService(metadata_inferrer=FakeInferrer(), providers=[FakeProvider()])

    caplog.set_level(logging.DEBUG)
    payload = await service.resolve_lyrics(title="Raw Song", artist="Raw Artist", youtube_title="YouTube Song")

    assert payload is None
    messages = "\n".join(record.message for record in caplog.records)
    assert "Got YouTube title='YouTube Song'" in messages
    assert "Searching provider=lrclib" in messages
    assert "lyrics not found" in messages


@pytest.mark.asyncio
async def test_lyrics_service_fallback_providers_run_concurrently_and_pick_best_score():
    """Fallback providers should run together and return the highest-scoring payload."""
    from services import lyrics_service as ls_module

    inferred = ls_module.InferredSong(title="Song", artist="Artist", source="regex")

    class FakeInferrer:
        async def infer(self, title: str, artist: str | None = None):
            return inferred

    class WaitingProvider:
        def __init__(self, name: str, score: float):
            self.name = name
            self.score = score
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = 0

        async def fetch(self, inferred_song):
            self.calls += 1
            self.started.set()
            await self.release.wait()
            return ls_module.LyricsPayload(
                lyrics=f"{self.name} line",
                is_synced=True,
                provider=self.name,
                inferred_song=inferred_song,
                provider_score=self.score,
            )

    slow_low = WaitingProvider("netease", 50.0)
    slow_high = WaitingProvider("lrclib", 80.0)
    service = LyricsService(metadata_inferrer=FakeInferrer(), providers=[slow_low, slow_high])

    task = asyncio.create_task(service.resolve_lyrics(title="Song", artist="Artist"))
    await asyncio.wait_for(slow_low.started.wait(), timeout=1)
    await asyncio.wait_for(slow_high.started.wait(), timeout=1)
    slow_low.release.set()
    slow_high.release.set()
    payload = await asyncio.wait_for(task, timeout=1)

    assert payload is not None
    assert payload.provider == "lrclib"
    assert slow_low.calls == 1
    assert slow_high.calls == 1


def test_lyrics_service_default_provider_order_includes_netease_between_musixmatch_and_lrclib():
    """Default provider chain should keep NetEase between Musixmatch and LRCLib."""
    original_token = settings.musixmatch_token
    original_netease_enabled = settings.lyrics_provider_netease_enabled
    original_lrclib_enabled = settings.lyrics_provider_lrclib_enabled
    try:
        settings.musixmatch_token = "token123"
        settings.lyrics_provider_netease_enabled = True
        settings.lyrics_provider_lrclib_enabled = True
        service = LyricsService()
    finally:
        settings.musixmatch_token = original_token
        settings.lyrics_provider_netease_enabled = original_netease_enabled
        settings.lyrics_provider_lrclib_enabled = original_lrclib_enabled

    provider_names = [provider.name for provider in service.providers]
    assert provider_names == ["musixmatch", "netease", "lrclib"]


def test_lyrics_service_default_provider_order_respects_runtime_toggles():
    """Default provider list should honor runtime enable/disable toggles."""
    original_token = settings.musixmatch_token
    original_netease_enabled = settings.lyrics_provider_netease_enabled
    original_lrclib_enabled = settings.lyrics_provider_lrclib_enabled
    try:
        settings.musixmatch_token = "token123"
        settings.lyrics_provider_netease_enabled = False
        settings.lyrics_provider_lrclib_enabled = True
        service = LyricsService()
        provider_names = [provider.name for provider in service.providers]
    finally:
        settings.musixmatch_token = original_token
        settings.lyrics_provider_netease_enabled = original_netease_enabled
        settings.lyrics_provider_lrclib_enabled = original_lrclib_enabled

    assert provider_names == ["musixmatch", "lrclib"]


@pytest.mark.asyncio
async def test_lyrics_service_rebuilds_default_providers_on_each_resolve():
    """Default provider selection should refresh from runtime settings without recreating the service."""
    from services import lyrics_service as ls_module

    inferred = ls_module.InferredSong(title="Song", artist="Artist", source="regex")

    class FakeInferrer:
        async def infer(self, title: str, artist: str | None = None):
            return inferred

    class FakeProvider:
        def __init__(self, name: str):
            self.name = name

        async def fetch(self, inferred_song):
            return ls_module.LyricsPayload(
                lyrics=f"{self.name}-lyrics",
                is_synced=True,
                provider=self.name,
                inferred_song=inferred_song,
                provider_score=1.0,
            )

    service = LyricsService(metadata_inferrer=FakeInferrer())
    netease_provider = FakeProvider("netease")
    lrclib_provider = FakeProvider("lrclib")

    original_netease_enabled = settings.lyrics_provider_netease_enabled
    original_lrclib_enabled = settings.lyrics_provider_lrclib_enabled
    original_builder = service._build_default_providers
    try:
        def fake_builder():
            if settings.lyrics_provider_netease_enabled:
                return [netease_provider]
            if settings.lyrics_provider_lrclib_enabled:
                return [lrclib_provider]
            return []

        service._build_default_providers = fake_builder  # type: ignore[assignment]
        settings.lyrics_provider_netease_enabled = True
        settings.lyrics_provider_lrclib_enabled = False
        first = await service.resolve_lyrics("Song", "Artist")

        settings.lyrics_provider_netease_enabled = False
        settings.lyrics_provider_lrclib_enabled = True
        second = await service.resolve_lyrics("Song", "Artist")
    finally:
        service._build_default_providers = original_builder
        settings.lyrics_provider_netease_enabled = original_netease_enabled
        settings.lyrics_provider_lrclib_enabled = original_lrclib_enabled

    assert first is not None
    assert first.provider == "netease"
    assert second is not None
    assert second.provider == "lrclib"


@pytest.mark.asyncio
async def test_netease_provider_fetches_synced_and_merges_translation():
    """NetEase provider should merge translated lines when synced timestamps match."""
    from services import lyrics_service as ls_module

    provider = ls_module.NeteaseLyricsProvider()
    provider._weapi_encrypt = lambda payload: {"params": "encrypted", "encSecKey": "key"}  # type: ignore[attr-defined]

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data, headers):
            if "weapi/search/get" in url:
                return FakeResponse(
                    {
                        "code": 200,
                        "result": {
                            "songs": [
                                {
                                    "id": 12345,
                                    "name": "Song A",
                                    "duration": 123000,
                                    "album": {"name": "Album A"},
                                    "artists": [{"name": "Artist A"}],
                                }
                            ]
                        },
                    }
                )
            if "weapi/song/lyric" in url:
                return FakeResponse(
                    {
                        "code": 200,
                        "lrc": {"lyric": "[00:01.00]Hello\n[00:02.00]World"},
                        "tlyric": {"lyric": "[00:01.00]你好\n[00:02.00]世界"},
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

        async def get(self, url, params, headers):
            raise AssertionError(f"Legacy endpoint should not be used: {url}")

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        payload = await provider.fetch(
            ls_module.InferredSong(title="Song A", artist="Artist A", source="regex")
        )
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert payload is not None
    assert payload.provider == "netease"
    assert payload.is_synced is True
    assert payload.lyrics == "[00:01.00]Hello/你好\n[00:02.00]World/世界"
    assert payload.provider_details is not None
    assert payload.provider_details["song_id"] == 12345
    assert payload.provider_details["selected_query"] is not None
    assert payload.provider_details["queries_tried"]


@pytest.mark.asyncio
async def test_netease_provider_falls_back_to_legacy_api_when_weapi_unavailable():
    """NetEase provider should continue via legacy endpoints when weapi encryption is unavailable."""
    from services import lyrics_service as ls_module

    provider = ls_module.NeteaseLyricsProvider()

    def _raise_no_crypto(_: dict):
        raise RuntimeError("no crypto")

    provider._weapi_encrypt = _raise_no_crypto  # type: ignore[attr-defined]

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data, headers):
            raise AssertionError(f"weapi endpoint should not be used: {url}")

        async def get(self, url, params, headers):
            if "api/search/get" in url:
                return FakeResponse(
                    {
                        "code": 200,
                        "result": {
                            "songs": [
                                {
                                    "id": 8888,
                                    "name": "Legacy Song",
                                    "duration": 111000,
                                    "album": {"name": "Legacy Album"},
                                    "artists": [{"name": "Legacy Artist"}],
                                }
                            ]
                        },
                    }
                )
            if "api/song/lyric" in url:
                return FakeResponse(
                    {
                        "code": 200,
                        "lrc": {"lyric": "Line 1\nLine 2"},
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

    original_client = ls_module.httpx.AsyncClient
    try:
        ls_module.httpx.AsyncClient = FakeAsyncClient
        payload = await provider.fetch(
            ls_module.InferredSong(title="Legacy Song", artist="Legacy Artist", source="regex")
        )
    finally:
        ls_module.httpx.AsyncClient = original_client

    assert payload is not None
    assert payload.provider == "netease"
    assert payload.is_synced is False
    assert payload.lyrics == "Line 1\nLine 2"


@pytest.mark.asyncio
async def test_netease_provider_stops_after_high_confidence_match():
    """A strong early match should avoid extra NetEase search requests."""
    from services import lyrics_providers as lp_module
    from services import lyrics_service as ls_module

    provider = ls_module.NeteaseLyricsProvider()
    queries_seen: list[str] = []
    best_candidate = lp_module._NeteaseSongCandidate(
        song_id=543798364,
        title="月亮惹的祸",
        artists=["张宇"],
        album="月亮 太阳",
        duration_ms=262466,
    )

    async def fake_request_search(query: str):
        queries_seen.append(query)
        return [best_candidate]

    async def fake_request_lyrics(song_id: int):
        assert song_id == 543798364
        return {
            "code": 200,
            "lrc": {"lyric": "[00:01.00]Hello"},
            "tlyric": {"lyric": "[00:01.00]你好"},
        }

    provider._request_search = fake_request_search  # type: ignore[method-assign]
    provider._request_lyrics = fake_request_lyrics  # type: ignore[method-assign]

    payload = await provider.fetch(
        ls_module.InferredSong(
            title="月亮惹的禍 Troubled By The Moon",
            artist="張宇 Phil Chang",
            source="lastfm",
        )
    )

    assert payload is not None
    assert payload.provider == "netease"
    assert queries_seen == [queries_seen[0]]
    assert len(queries_seen) == 1


def test_netease_provider_prefers_cjk_candidate_and_rejects_low_confidence():
    """Candidate selector should avoid unrelated songs and pick CJK-near matches."""
    from services import lyrics_providers as lp_module
    from services import lyrics_service as ls_module

    inferred = ls_module.InferredSong(
        title="月亮惹的禍 Troubled By The Moon",
        artist="張宇 Phil Chang",
        source="lastfm",
    )

    unrelated = lp_module._NeteaseSongCandidate(
        song_id=2051231725,
        title="Üher",
        artists=["NaraBara"],
        album="Other",
        duration_ms=180000,
    )
    expected = lp_module._NeteaseSongCandidate(
        song_id=190526,
        title="月亮惹的祸",
        artists=["张宇"],
        album="月亮 太阳",
        duration_ms=262466,
    )

    selected = lp_module.NeteaseLyricsProvider._select_best_candidate(
        [unrelated, expected], inferred
    )
    assert selected is not None
    assert selected.song_id == 190526

    low_conf_only = lp_module.NeteaseLyricsProvider._select_best_candidate([unrelated], inferred)
    assert low_conf_only is None


@pytest.mark.asyncio
async def test_media_karaoke_audio_only_uses_instrumental_as_primary(
    db_session, tmp_path
):
    """Audio uploads should finalize without trying to map a video stream."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        original_file = settings.media_path / "audio-karaoke.mp3"
        original_file.write_bytes(b"original-audio")
        media = MediaItem(
            file_stem="audio-karaoke",
            title="Audio Karaoke",
            media_path="/media/audio-karaoke.mp3",
            missing=False,
        )
        db_session.add(media)
        db_session.commit()
        db_session.refresh(media)
        task = processing_task_service.get_or_create_media_task(db_session, media.id)

        no_vocals = settings.cache_path / "demucs_outputs" / "audio-karaoke.no_vocals.wav"
        vocals = settings.cache_path / "demucs_outputs" / "audio-karaoke.vocals.wav"
        no_vocals.parent.mkdir(parents=True, exist_ok=True)
        no_vocals.write_bytes(b"instrumental")
        vocals.write_bytes(b"guide-vocals")

        service = KaraokeService()
        service.ffmpeg = Mock()
        service.demucs_client = Mock()
        service.demucs_client.health_check.return_value = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=True,
            detail="ok",
        )
        service.demucs_client.separate_vocals = AsyncMock(
            return_value=DemucsResponse(
                no_vocals_path=str(no_vocals),
                vocals_path=str(vocals),
            )
        )

        await service.process_task(db_session, task.id)

        db_session.refresh(media)
        db_session.refresh(task)
        assert task.status == ProcessingTaskStatus.DONE.value
        assert media.media_path == "/media/audio-karaoke.wav"
        assert media.vocals_path == "/media/audio-karaoke.vocals.wav"
        assert (settings.media_path / "audio-karaoke.wav").read_bytes() == b"instrumental"
        assert (settings.media_path / "audio-karaoke.vocals.wav").read_bytes() == b"guide-vocals"
        assert not original_file.exists()
        service.ffmpeg.extract_audio.assert_not_called()
        service.ffmpeg.combine_audio_video.assert_not_called()
        await task_stream_manager.clear_task(task.id)
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache


@pytest.mark.asyncio
async def test_karaoke_service_small_local_video_uses_direct_media_for_demucs(
    db_session, tmp_path
):
    """Small local video files should go directly to Demucs."""
    queue_service = QueueService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    original_cutoff = settings.demucs_direct_media_max_mb
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.demucs_direct_media_max_mb = 1
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        expected_stem = build_media_stem("Direct Local", "Singer", fallback="direct-local")
        media_file = settings.media_path / f"{expected_stem}.mp4"
        media_file.write_bytes(b"video")
        db_session.add(
            MediaItem(
                file_stem=expected_stem,
                title="Direct Local",
                artist="Singer",
                media_path=f"/media/{expected_stem}.mp4",
                missing=False,
            )
        )
        db_session.flush()

        item = queue_service.add_to_queue(
            db_session,
            QueueItemCreate(
                media_item_id=db_session.query(MediaItem).filter(MediaItem.file_stem == expected_stem).first().id,
                title="Direct Local",
                artist="Singer",
                is_karaoke=True,
            ),
        )

        service = KaraokeService()
        service.queue_service = queue_service
        service.youtube_service = Mock()
        service.ffmpeg = Mock()
        service.demucs_client = Mock()
        service.demucs_client.health_check.return_value = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=True,
            detail="ok",
        )
        no_vocals = settings.cache_path / "demucs_outputs" / f"{expected_stem}.no_vocals.wav"
        vocals = settings.cache_path / "demucs_outputs" / f"{expected_stem}.vocals.wav"
        no_vocals.parent.mkdir(parents=True, exist_ok=True)
        no_vocals.write_bytes(b"instrumental")
        vocals.write_bytes(b"vocals")
        service.demucs_client.separate_vocals = AsyncMock(
            return_value=DemucsResponse(
                no_vocals_path=str(no_vocals),
                vocals_path=str(vocals),
            )
        )

        def fake_combine_audio_video(*, video_path, audio_path, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"karaoke-video")

        service.ffmpeg.combine_audio_video.side_effect = fake_combine_audio_video

        await service.process_queue_item(db_session, item.id)

        service.ffmpeg.extract_audio.assert_not_called()
        service.youtube_service.download_audio.assert_not_called()
        assert service.demucs_client.separate_vocals.await_args.args[0] == media_file
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
        settings.demucs_direct_media_max_mb = original_cutoff


@pytest.mark.asyncio
async def test_karaoke_service_large_local_video_extracts_audio_for_demucs(
    db_session, tmp_path
):
    """Large local video files should extract audio before Demucs."""
    queue_service = QueueService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    original_cutoff = settings.demucs_direct_media_max_mb
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.demucs_direct_media_max_mb = 1
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        expected_stem = build_media_stem("Large Local", "Singer", fallback="large-local")
        media_file = settings.media_path / f"{expected_stem}.mp4"
        media_file.write_bytes(b"video" * 300000)
        db_session.add(
            MediaItem(
                file_stem=expected_stem,
                title="Large Local",
                artist="Singer",
                media_path=f"/media/{expected_stem}.mp4",
                missing=False,
            )
        )
        db_session.flush()

        media_row = db_session.query(MediaItem).filter(MediaItem.file_stem == expected_stem).first()
        assert media_row is not None
        item = queue_service.add_to_queue(
            db_session,
            QueueItemCreate(
                media_item_id=media_row.id,
                title="Large Local",
                artist="Singer",
                is_karaoke=True,
            ),
        )

        service = KaraokeService()
        service.queue_service = queue_service
        service.youtube_service = Mock()
        service.ffmpeg = Mock()
        service.demucs_client = Mock()
        service.demucs_client.health_check.return_value = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=True,
            detail="ok",
        )
        extracted_audio = settings.cache_path / "audio" / f"{expected_stem}.audio.m4a"
        extracted_audio.parent.mkdir(parents=True, exist_ok=True)
        extracted_audio.write_bytes(b"audio")
        service.ffmpeg.extract_audio.return_value = extracted_audio
        no_vocals = settings.cache_path / "demucs_outputs" / f"{expected_stem}.no_vocals.wav"
        vocals = settings.cache_path / "demucs_outputs" / f"{expected_stem}.vocals.wav"
        no_vocals.parent.mkdir(parents=True, exist_ok=True)
        no_vocals.write_bytes(b"instrumental")
        vocals.write_bytes(b"vocals")
        service.demucs_client.separate_vocals = AsyncMock(
            return_value=DemucsResponse(
                no_vocals_path=str(no_vocals),
                vocals_path=str(vocals),
            )
        )

        def fake_combine_audio_video(*, video_path, audio_path, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"karaoke-video")

        service.ffmpeg.combine_audio_video.side_effect = fake_combine_audio_video

        await service.process_queue_item(db_session, item.id)

        service.youtube_service.download_audio.assert_not_called()
        service.ffmpeg.extract_audio.assert_called_once_with(
            media_file,
            extracted_audio,
            cancel_event=None,
        )
        assert service.demucs_client.separate_vocals.await_args.args[0] == extracted_audio
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
        settings.demucs_direct_media_max_mb = original_cutoff


@pytest.mark.asyncio
async def test_karaoke_service_small_youtube_video_uses_direct_media_for_demucs(
    db_session, tmp_path
):
    """Small YouTube downloads should go directly to Demucs without audio re-download."""
    queue_service = QueueService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    original_cutoff = settings.demucs_direct_media_max_mb
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.demucs_direct_media_max_mb = 1
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        expected_stem = build_media_stem("Small Direct", "Singer", fallback="small-direct")
        item = queue_service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="small-direct",
                title="Small Direct",
                artist="Singer",
                is_karaoke=True,
            ),
        )

        service = KaraokeService()
        service.queue_service = queue_service
        service.youtube_service = Mock()
        service.ffmpeg = Mock()
        service.demucs_client = Mock()
        service.demucs_client.health_check.return_value = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=True,
            detail="ok",
        )
        downloaded_video = settings.cache_path / "small-direct.mp4"
        downloaded_video.write_bytes(b"video")
        service.youtube_service.download_video.return_value = downloaded_video
        no_vocals = settings.cache_path / "demucs_outputs" / "small-direct.no_vocals.wav"
        vocals = settings.cache_path / "demucs_outputs" / "small-direct.vocals.wav"
        no_vocals.parent.mkdir(parents=True, exist_ok=True)
        no_vocals.write_bytes(b"instrumental")
        vocals.write_bytes(b"vocals")
        service.demucs_client.separate_vocals = AsyncMock(
            return_value=DemucsResponse(
                no_vocals_path=str(no_vocals),
                vocals_path=str(vocals),
            )
        )

        def fake_combine_audio_video(*, video_path, audio_path, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"karaoke-video")

        service.ffmpeg.combine_audio_video.side_effect = fake_combine_audio_video

        await service.process_queue_item(db_session, item.id)

        service.youtube_service.download_video.assert_called_once_with(
            "small-direct",
            settings.cache_path / "ytdlp",
        )
        service.youtube_service.download_audio.assert_not_called()
        service.ffmpeg.extract_audio.assert_not_called()
        assert service.demucs_client.separate_vocals.await_args.args[0] == (
            settings.cache_path / f"{expected_stem}.mp4"
        )
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
        settings.demucs_direct_media_max_mb = original_cutoff


@pytest.mark.asyncio
async def test_karaoke_service_large_youtube_video_uses_audio_only_for_demucs(
    db_session, tmp_path
):
    """Large YouTube downloads should fall back to the audio-only path for Demucs."""
    queue_service = QueueService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    original_cutoff = settings.demucs_direct_media_max_mb
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.demucs_direct_media_max_mb = 1
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        expected_stem = build_media_stem("Large Audio", "Singer", fallback="large-audio")
        item = queue_service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="large-audio",
                title="Large Audio",
                artist="Singer",
                is_karaoke=True,
            ),
        )

        service = KaraokeService()
        service.queue_service = queue_service
        service.youtube_service = Mock()
        service.ffmpeg = Mock()
        service.demucs_client = Mock()
        service.demucs_client.health_check.return_value = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=True,
            detail="ok",
        )
        downloaded_video = settings.cache_path / "large-audio.mp4"
        downloaded_video.write_bytes(b"video" * 300000)
        downloaded_audio = settings.cache_path / "large-audio.audio.m4a"
        downloaded_audio.write_bytes(b"audio")
        service.youtube_service.download_video.return_value = downloaded_video
        service.youtube_service.download_audio.return_value = downloaded_audio
        no_vocals = settings.cache_path / "demucs_outputs" / "large-audio.no_vocals.wav"
        vocals = settings.cache_path / "demucs_outputs" / "large-audio.vocals.wav"
        no_vocals.parent.mkdir(parents=True, exist_ok=True)
        no_vocals.write_bytes(b"instrumental")
        vocals.write_bytes(b"vocals")
        service.demucs_client.separate_vocals = AsyncMock(
            return_value=DemucsResponse(
                no_vocals_path=str(no_vocals),
                vocals_path=str(vocals),
            )
        )

        def fake_combine_audio_video(*, video_path, audio_path, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"karaoke-video")

        service.ffmpeg.combine_audio_video.side_effect = fake_combine_audio_video

        await service.process_queue_item(db_session, item.id)

        service.youtube_service.download_video.assert_called_once_with(
            "large-audio",
            settings.cache_path / "ytdlp",
        )
        service.youtube_service.download_audio.assert_called_once_with(
            "large-audio",
            settings.cache_path / "ytdlp",
        )
        service.ffmpeg.extract_audio.assert_not_called()
        assert service.demucs_client.separate_vocals.await_args.args[0] == (
            settings.cache_path / f"{expected_stem}.audio.m4a"
        )
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
        settings.demucs_direct_media_max_mb = original_cutoff


@pytest.mark.asyncio
async def test_karaoke_service_karaoke_without_burn_uses_remux(db_session, tmp_path):
    """Karaoke processing should remux final output instead of burning subtitles."""
    queue_service = QueueService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    original_cutoff = settings.demucs_direct_media_max_mb
    settings.media_path = tmp_path / "media"
    settings.media_path.mkdir(parents=True, exist_ok=True)
    settings.cache_path = tmp_path / "cache"
    settings.cache_path.mkdir(parents=True, exist_ok=True)
    settings.demucs_direct_media_max_mb = 0
    item = queue_service.add_to_queue(
        db_session,
        QueueItemCreate(
            youtube_id="kara123",
            title="Kara Song",
            artist="Singer",
            is_karaoke=True,
        ),
    )

    service = KaraokeService()
    service.queue_service = queue_service
    service.youtube_service = Mock()
    service.demucs_client = Mock()
    service.ffmpeg = Mock()
    expected_stem = build_media_stem("Kara Song", "Singer", fallback="kara123")
    downloaded_video = settings.cache_path / "kara123.mp4"
    downloaded_audio = settings.cache_path / "kara123.audio.m4a"
    downloaded_video.write_text("video", encoding="utf-8")
    downloaded_audio.write_text("audio", encoding="utf-8")
    service.youtube_service.download_video.return_value = downloaded_video
    service.youtube_service.download_audio.return_value = downloaded_audio
    no_vocals_file = tmp_path / f"{expected_stem}.no_vocals.wav"
    vocals_file = tmp_path / f"{expected_stem}.vocals.wav"
    no_vocals_file.write_bytes(b"no-vocals")
    vocals_file.write_bytes(b"vocals")
    def fake_combine_audio_video(*, video_path, audio_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"karaoke-video")
    service.demucs_client.separate_vocals = AsyncMock(
        return_value=Mock(no_vocals_path=str(no_vocals_file), vocals_path=str(vocals_file))
    )
    service.ffmpeg.combine_audio_video.side_effect = fake_combine_audio_video
    try:
        expected_media_file = settings.media_path / f"{expected_stem}.mp4"
        expected_vocals_file = settings.media_path / f"{expected_stem}.vocals.wav"
        await service.process_queue_item(db_session, item.id)
        service.youtube_service.download_video.assert_called_once_with(
            "kara123",
            settings.cache_path / "ytdlp",
        )
        service.youtube_service.download_audio.assert_called_once_with(
            "kara123",
            settings.cache_path / "ytdlp",
        )
        assert expected_media_file.exists()
        assert expected_vocals_file.exists()
    finally:
        settings.cache_path = original_cache
        settings.media_path = original_media
        settings.demucs_direct_media_max_mb = original_cutoff

    service.ffmpeg.combine_audio_video.assert_called_once()
    updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
    assert updated_item is not None
    assert updated_item.media is not None
    assert updated_item.media.media_path == f"/media/{expected_stem}.mp4"
    assert updated_item.media.vocals_path == f"/media/{expected_stem}.vocals.wav"


@pytest.mark.asyncio
async def test_karaoke_service_reuses_existing_media_without_redownload(db_session, tmp_path):
    """Existing downloaded media should skip yt-dlp download work for non-karaoke items."""
    service = KaraokeService()
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        expected_stem = build_media_stem("Reuse Song", "Singer", fallback="reuse001")
        (settings.media_path / "reuse001.mp4").write_text("video", encoding="utf-8")

        db_session.add(
            MediaItem(
                youtube_id="reuse001",
                title="Reuse Song",
                artist="Singer",
                media_path="/media/reuse001.mp4",
                missing=False,
            )
        )
        db_session.flush()

        item = service.queue_service.add_to_queue(
            db_session,
            QueueItemCreate(youtube_id="reuse001", title="Reuse Song", is_karaoke=False),
        )

        service.youtube_service = Mock()
        service.ffmpeg = Mock()

        await service.process_queue_item(db_session, item.id)

        service.youtube_service.download_video_with_audio.assert_not_called()
        updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
        assert updated_item is not None
        assert updated_item.status == QueueStatus.PLAYING
        assert updated_item.media is not None
        assert updated_item.media.media_path == f"/media/{expected_stem}.mp4"
    finally:
        settings.media_path = original_media


@pytest.mark.asyncio
async def test_karaoke_service_reuses_existing_karaoke_media_without_redownload(
    db_session, tmp_path
):
    """Previously processed karaoke media should be reused without re-downloading."""
    service = KaraokeService()
    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        expected_stem = build_media_stem("Karaoke Reuse", "Singer", fallback="kara-reuse")
        (settings.media_path / "kara-reuse.mp4").write_text("video", encoding="utf-8")
        (settings.media_path / "kara-reuse.vocals.mp3").write_text("vocals", encoding="utf-8")

        db_session.add(
            MediaItem(
                youtube_id="kara-reuse",
                title="Karaoke Reuse",
                artist="Singer",
                media_path="/media/kara-reuse.mp4",
                vocals_path="/media/kara-reuse.vocals.mp3",
                missing=False,
            )
        )
        db_session.flush()

        item = service.queue_service.add_to_queue(
            db_session,
            QueueItemCreate(
                youtube_id="kara-reuse", title="Karaoke Reuse", is_karaoke=True
            ),
        )

        service.youtube_service = Mock()
        service.ffmpeg = Mock()

        await service.process_queue_item(db_session, item.id)

        service.youtube_service.download_video.assert_not_called()
        service.youtube_service.download_audio.assert_not_called()
        service.ffmpeg.extract_audio.assert_not_called()
        updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
        assert updated_item is not None
        assert updated_item.status == QueueStatus.PLAYING
        assert updated_item.media is not None
        assert updated_item.media.media_path == f"/media/{expected_stem}.mp4"
        assert updated_item.media.vocals_path == f"/media/{expected_stem}.vocals.mp3"
    finally:
        settings.media_path = original_media


@pytest.mark.asyncio
async def test_karaoke_service_retries_demucs_with_downloaded_audio_after_500(
    db_session, tmp_path
):
    """Retry Demucs once with yt-dlp audio when extracted local audio fails with HTTP 500."""
    service = KaraokeService()
    original_media = settings.media_path
    original_cache = settings.cache_path
    original_cutoff = settings.demucs_direct_media_max_mb
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.demucs_direct_media_max_mb = 0
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)
        (settings.media_path / "retry001.mp4").write_text("video", encoding="utf-8")

        db_session.add(
            MediaItem(
                youtube_id="retry001",
                title="Retry Song",
                artist="Singer",
                media_path="/media/retry001.mp4",
                missing=False,
            )
        )
        db_session.flush()

        item = service.queue_service.add_to_queue(
            db_session,
            QueueItemCreate(youtube_id="retry001", title="Retry Song", is_karaoke=True),
        )

        service.youtube_service = Mock()
        service.ffmpeg = Mock()
        service.demucs_client = Mock()
        service.demucs_client.health_check.return_value = DemucsHealthResponse(
            api_url="http://demucs",
            healthy=True,
            detail="ok",
        )

        extracted_audio = settings.cache_path / "audio" / "retry001.m4a"
        fallback_audio = settings.cache_path / "retry001.m4a"
        fallback_audio.write_text("audio", encoding="utf-8")
        service.ffmpeg.extract_audio.return_value = extracted_audio
        service.youtube_service.download_audio.return_value = fallback_audio

        no_vocals_file = settings.cache_path / "stem" / "retry001.no_vocals.wav"
        vocals_file = settings.cache_path / "stem" / "retry001.vocals.wav"
        no_vocals_file.parent.mkdir(parents=True, exist_ok=True)
        no_vocals_file.write_bytes(b"no-vocals")
        vocals_file.write_bytes(b"vocals")

        request = httpx.Request("POST", "http://demucs/separate")
        response = httpx.Response(500, request=request)
        demucs_error = httpx.HTTPStatusError("500", request=request, response=response)
        service.demucs_client.separate_vocals = AsyncMock(
            side_effect=[
                demucs_error,
                DemucsResponse(
                    no_vocals_path=str(no_vocals_file),
                    vocals_path=str(vocals_file),
                ),
            ]
        )
        def fake_combine_audio_video(*, video_path, audio_path, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"karaoke-video")
        service.ffmpeg.combine_audio_video.side_effect = fake_combine_audio_video

        await service.process_queue_item(db_session, item.id)

        service.youtube_service.download_audio.assert_called_once_with(
            "retry001",
            settings.cache_path / "ytdlp",
        )
        assert service.demucs_client.separate_vocals.await_count == 2
        updated_item = db_session.query(QueueItem).filter(QueueItem.id == item.id).first()
        assert updated_item is not None
        assert updated_item.status == QueueStatus.PLAYING
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
        settings.demucs_direct_media_max_mb = original_cutoff


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


def test_lyrics_service_parse_lrc_to_cues_with_offset_and_multi_timestamps():
    """LRC parser should support offsets and multiple timestamps per line."""
    service = LyricsService()
    lyrics = "\n".join(
        [
            "[offset:500]",
            "[00:00.00][00:02.00]Hello line",
            "[00:04.50]Next line",
        ]
    )

    cues = service.parse_lrc_to_cues(lyrics)

    assert cues == [
        {"time": 0.5, "text": "Hello line"},
        {"time": 2.5, "text": "Hello line"},
        {"time": 5.0, "text": "Next line"},
    ]


def test_lyrics_service_parse_json_to_cues_normalizes_shape():
    """JSON parser should accept alternate time/text keys and sort cues."""
    service = LyricsService()
    payload = """
    {
        "cues": [
            {"start": 5.2, "line": "Later line"},
            {"time": 1.0, "text": "First line"},
            {"timestamp": 3.4, "lyric": "Middle line"}
        ]
    }
    """

    cues = service.parse_json_to_cues(payload)

    assert cues == [
        {"time": 1.0, "text": "First line"},
        {"time": 3.4, "text": "Middle line"},
        {"time": 5.2, "text": "Later line"},
    ]


def test_lyrics_service_parse_json_to_cues_accepts_aligned_segments():
    """JSON parser should normalize WhisperX-style aligned segments into line cues."""
    service = LyricsService()
    payload = json.dumps(
        {
            "segments": [
                {
                    "start": 2.5,
                    "end": 4.0,
                    "text": "Hello world",
                    "words": [
                        {"word": "Hello", "start": 2.5, "end": 3.0},
                        {"word": "world", "start": 3.0, "end": 4.0},
                    ],
                },
                {
                    "start": 5.25,
                    "end": 6.25,
                    "words": [
                        {"word": "Second", "start": 5.25, "end": 5.75},
                        {"word": "line", "start": 5.75, "end": 6.25},
                    ],
                },
            ]
        }
    )

    cues = service.parse_json_to_cues(payload)

    assert cues == [
        {
            "time": 2.5,
            "text": "Hello world",
            "words": [
                {"word": "Hello", "start": 2.5, "end": 3.0},
                {"word": "world", "start": 3.0, "end": 4.0},
            ],
        },
        {
            "time": 5.25,
            "text": "Second line",
            "words": [
                {"word": "Second", "start": 5.25, "end": 5.75},
                {"word": "line", "start": 5.75, "end": 6.25},
            ],
        },
    ]


def test_lyrics_service_parse_json_to_cues_ignores_invalid_aligned_words():
    """JSON parser should keep line cues when nested word timing is unusable."""
    service = LyricsService()
    payload = json.dumps(
        [
            {
                "start": 1.0,
                "text": "Keep this line",
                "words": [
                    {"word": "Keep", "start": 1.0, "end": 1.2},
                    {"word": "missing end", "start": 1.0},
                    {"word": "backwards", "start": 2.0, "end": 1.5},
                    {"word": "", "start": 1.0, "end": 1.5},
                ],
            }
        ]
    )

    assert service.parse_json_to_cues(payload) == [
        {"time": 1.0, "text": "Keep this line"}
    ]


def test_chinese_lyrics_service_simplifies_and_adds_pinyin():
    """Chinese lyrics transformer should simplify Traditional Chinese and preserve mixed text."""
    service = ChineseLyricsService()

    items = service.transform_lines(
        [
            "繁體中文",
            "Hello 世界",
            "No Chinese here",
        ],
        include_pinyin=True,
    )

    assert items[0]["simplified"] == "繁体中文"
    assert items[0]["has_chinese"] is True
    assert items[0]["pinyin"] == "fan ti zhong wen"
    assert items[1]["simplified"] == "Hello 世界"
    assert items[1]["pinyin"] == "Hello shi jie"
    assert items[2]["simplified"] == "No Chinese here"
    assert items[2]["pinyin"] is None


@pytest.mark.asyncio
async def test_demucs_client_upload_and_save(tmp_path):
    """Demucs client should submit, poll, download ZIP result, and save stems."""
    src = tmp_path / "input.wav"
    src.write_bytes(b"fake-audio-bytes")
    progress_events = []
    log_events = []

    class FakeResponse:
        def __init__(self, *, json_payload=None, content=b"", headers=None, status_code=200):
            self.status_code = status_code
            self._json_payload = json_payload
            self.content = content
            self.headers = headers or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_payload

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout
            self.status_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, files, data):
            assert url.endswith("/jobs")
            assert "file" in files
            assert data["model"] == "htdemucs"
            assert data["device"] == "cuda"
            assert data["output_format"] == "wav"
            assert data["transcription_model"] == "tiny"
            assert data["align_language"] == "en"
            assert data["detect_language"] == "false"
            assert data["use_synced_lyrics"] == "false"
            assert "whisperx_preload_models" in data
            return FakeResponse(
                json_payload={
                    "job_id": "job123",
                    "status": "queued",
                    "progress_percent": 0,
                    "progress_message": "Queued",
                }
            )

        async def get(self, url):
            if url.endswith("/jobs/job123"):
                self.status_calls += 1
                if self.status_calls == 1:
                    return FakeResponse(
                        json_payload={
                            "job_id": "job123",
                            "status": "running",
                            "progress_percent": 41,
                            "progress_message": "Separating vocals",
                            "output_tail": ["Demucs boot", "41%|####"],
                        }
                    )
                return FakeResponse(
                    json_payload={
                        "job_id": "job123",
                        "status": "completed",
                        "progress_percent": 100,
                        "progress_message": "Completed",
                        "output_tail": ["Demucs boot", "41%|####", "Completed"],
                    }
                )
            if url.endswith("/jobs/job123/result"):
                buffer = BytesIO()
                with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("no_vocals.wav", b"no-vocals-wav")
                    archive.writestr("vocals.wav", b"vocals-wav")
                return FakeResponse(content=buffer.getvalue())
            raise AssertionError(f"Unexpected GET {url}")

        async def delete(self, url):
            raise AssertionError(f"Unexpected DELETE {url}")

    from services import demucs_client as dc_module

    original_client = dc_module.httpx.AsyncClient
    original_cache = dc_module.settings.cache_path
    original_demucs_model = dc_module.settings.demucs_model
    original_demucs_device = dc_module.settings.demucs_device
    original_demucs_output_format = dc_module.settings.demucs_output_format
    original_demucs_mp3_bitrate = dc_module.settings.demucs_mp3_bitrate
    original_whisperx_transcription_model = dc_module.settings.whisperx_transcription_model
    original_whisperx_align_language = dc_module.settings.whisperx_align_language
    original_whisperx_detect_language = dc_module.settings.whisperx_detect_language
    original_whisperx_use_synced_lyrics = dc_module.settings.whisperx_use_synced_lyrics
    original_whisperx_preload_models = dc_module.settings.whisperx_preload_models
    original_poll_interval = dc_module.DemucsClient.POLL_INTERVAL_SECONDS
    try:
        dc_module.httpx.AsyncClient = FakeAsyncClient
        dc_module.settings.cache_path = tmp_path
        dc_module.settings.demucs_model = "htdemucs"
        dc_module.settings.demucs_device = "cuda"
        dc_module.settings.demucs_output_format = "wav"
        dc_module.settings.demucs_mp3_bitrate = 320
        dc_module.settings.whisperx_transcription_model = "tiny"
        dc_module.settings.whisperx_align_language = "en"
        dc_module.settings.whisperx_detect_language = False
        dc_module.settings.whisperx_use_synced_lyrics = False
        dc_module.settings.whisperx_preload_models = "transcription=tiny,align=en"
        dc_module.DemucsClient.POLL_INTERVAL_SECONDS = 0
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        result = await client.separate_vocals(
            src,
            progress_callback=lambda percent, message, metadata=None: progress_events.append((percent, message, metadata)),
            log_callback=lambda stream, message: log_events.append((stream, message)),
        )
    finally:
        dc_module.httpx.AsyncClient = original_client
        dc_module.settings.cache_path = original_cache
        dc_module.settings.demucs_model = original_demucs_model
        dc_module.settings.demucs_device = original_demucs_device
        dc_module.settings.demucs_output_format = original_demucs_output_format
        dc_module.settings.demucs_mp3_bitrate = original_demucs_mp3_bitrate
        dc_module.settings.whisperx_transcription_model = original_whisperx_transcription_model
        dc_module.settings.whisperx_align_language = original_whisperx_align_language
        dc_module.settings.whisperx_detect_language = original_whisperx_detect_language
        dc_module.settings.whisperx_use_synced_lyrics = original_whisperx_use_synced_lyrics
        dc_module.settings.whisperx_preload_models = original_whisperx_preload_models
        dc_module.DemucsClient.POLL_INTERVAL_SECONDS = original_poll_interval

    assert result.no_vocals_path.endswith("_job123_no_vocals.wav")
    assert result.vocals_path and result.vocals_path.endswith("_job123_vocals.wav")
    assert result.aligned_lyrics_path is None
    saved = Path(result.no_vocals_path)
    assert saved.exists()
    assert saved.read_bytes() == b"no-vocals-wav"
    vocals_saved = Path(result.vocals_path)
    assert vocals_saved.exists()
    assert vocals_saved.read_bytes() == b"vocals-wav"
    assert progress_events[0][0] == 0
    assert any(event[0] == 41 for event in progress_events)
    assert progress_events[-1][0] == 100
    assert ("remote", "Demucs boot") in log_events


@pytest.mark.asyncio
async def test_demucs_client_upload_and_save_with_aligned_lyrics(tmp_path):
    """Demucs client should extract aligned lyrics JSON when present in the zip."""
    src = tmp_path / "input.wav"
    src.write_bytes(b"fake-audio-bytes")

    class FakeResponse:
        def __init__(self, *, json_payload=None, content=b"", headers=None, status_code=200):
            self.status_code = status_code
            self._json_payload = json_payload
            self.content = content
            self.headers = headers or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_payload

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout
            self.status_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, files, data):
            return FakeResponse(
                json_payload={
                    "job_id": "job456",
                    "status": "queued",
                    "progress_percent": 0,
                    "progress_message": "Queued",
                }
            )

        async def get(self, url):
            if url.endswith("/jobs/job456"):
                self.status_calls += 1
                if self.status_calls == 1:
                    return FakeResponse(
                        json_payload={
                            "job_id": "job456",
                            "status": "running",
                            "progress_percent": 75,
                            "progress_message": "Aligning lyrics",
                            "output_tail": [],
                        }
                    )
                return FakeResponse(
                    json_payload={
                        "job_id": "job456",
                        "status": "completed",
                        "progress_percent": 100,
                        "progress_message": "Completed",
                        "output_tail": [],
                    }
                )
            if url.endswith("/jobs/job456/result"):
                buffer = BytesIO()
                with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("no_vocals.wav", b"no-vocals-wav")
                    archive.writestr("vocals.wav", b"vocals-wav")
                    archive.writestr(
                        "aligned_lyrics.json",
                        json.dumps(
                            [
                                {
                                    "start": 1.23,
                                    "end": 4.56,
                                    "text": "hello world",
                                    "words": [
                                        {"word": "hello", "start": 1.23, "end": 2.0, "score": 0.9},
                                        {"word": "world", "start": 2.1, "end": 4.56, "score": 0.8},
                                    ],
                                }
                            ],
                            ensure_ascii=False,
                        ).encode("utf-8"),
                    )
                return FakeResponse(content=buffer.getvalue())
            raise AssertionError(f"Unexpected GET {url}")

        async def delete(self, url):
            raise AssertionError(f"Unexpected DELETE {url}")

    from services import demucs_client as dc_module

    original_client = dc_module.httpx.AsyncClient
    original_cache = dc_module.settings.cache_path
    original_demucs_model = dc_module.settings.demucs_model
    original_demucs_device = dc_module.settings.demucs_device
    original_demucs_output_format = dc_module.settings.demucs_output_format
    original_demucs_mp3_bitrate = dc_module.settings.demucs_mp3_bitrate
    original_whisperx_transcription_model = dc_module.settings.whisperx_transcription_model
    original_whisperx_align_language = dc_module.settings.whisperx_align_language
    original_whisperx_detect_language = dc_module.settings.whisperx_detect_language
    original_whisperx_use_synced_lyrics = dc_module.settings.whisperx_use_synced_lyrics
    original_whisperx_preload_models = dc_module.settings.whisperx_preload_models
    original_poll_interval = dc_module.DemucsClient.POLL_INTERVAL_SECONDS
    try:
        dc_module.httpx.AsyncClient = FakeAsyncClient
        dc_module.settings.cache_path = tmp_path
        dc_module.settings.demucs_model = "htdemucs"
        dc_module.settings.demucs_device = "cuda"
        dc_module.settings.demucs_output_format = "wav"
        dc_module.settings.demucs_mp3_bitrate = 320
        dc_module.settings.whisperx_transcription_model = "tiny"
        dc_module.settings.whisperx_align_language = "en"
        dc_module.settings.whisperx_detect_language = False
        dc_module.settings.whisperx_use_synced_lyrics = False
        dc_module.settings.whisperx_preload_models = "transcription=tiny,align=en"
        dc_module.DemucsClient.POLL_INTERVAL_SECONDS = 0
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        result = await client.separate_vocals(
            src,
            lyrics_text="[00:01.00]hello world",
            lyrics_format="lrc",
            progress_callback=lambda percent, message, metadata=None: None,
            log_callback=lambda stream, message: None,
        )
    finally:
        dc_module.httpx.AsyncClient = original_client
        dc_module.settings.cache_path = original_cache
        dc_module.settings.demucs_model = original_demucs_model
        dc_module.settings.demucs_device = original_demucs_device
        dc_module.settings.demucs_output_format = original_demucs_output_format
        dc_module.settings.demucs_mp3_bitrate = original_demucs_mp3_bitrate
        dc_module.settings.whisperx_transcription_model = original_whisperx_transcription_model
        dc_module.settings.whisperx_align_language = original_whisperx_align_language
        dc_module.settings.whisperx_detect_language = original_whisperx_detect_language
        dc_module.settings.whisperx_use_synced_lyrics = original_whisperx_use_synced_lyrics
        dc_module.settings.whisperx_preload_models = original_whisperx_preload_models
        dc_module.DemucsClient.POLL_INTERVAL_SECONDS = original_poll_interval

    assert result.aligned_lyrics_path is not None
    aligned_path = Path(result.aligned_lyrics_path)
    assert aligned_path.exists()
    payload = json.loads(aligned_path.read_text(encoding="utf-8"))
    assert payload[0]["text"] == "hello world"
    assert len(payload[0]["words"]) == 2


@pytest.mark.asyncio
async def test_demucs_client_cancel_requests_remote_job(tmp_path):
    """Demucs client should cancel the remote job when local cancellation is set."""
    src = tmp_path / "input.wav"
    src.write_bytes(b"fake-audio-bytes")
    cancel_event = threading.Event()

    class FakeResponse:
        def __init__(self, *, json_payload=None):
            self.status_code = 200
            self._json_payload = json_payload
            self.content = b""
            self.headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._json_payload

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout
            self.deleted = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, files, data):
            return FakeResponse(
                json_payload={
                    "job_id": "job-cancel",
                    "status": "queued",
                    "progress_percent": 0,
                    "progress_message": "Queued",
                }
            )

        async def get(self, url):
            cancel_event.set()
            return FakeResponse(
                json_payload={
                    "job_id": "job-cancel",
                    "status": "running",
                    "progress_percent": 12,
                    "progress_message": "Separating vocals",
                    "output_tail": [],
                }
            )

        async def delete(self, url):
            self.deleted.append(url)
            return FakeResponse(json_payload={"job_id": "job-cancel", "status": "canceling"})

    from services import demucs_client as dc_module

    original_client = dc_module.httpx.AsyncClient
    original_poll_interval = dc_module.DemucsClient.POLL_INTERVAL_SECONDS
    try:
        fake_client = FakeAsyncClient(timeout=0)
        dc_module.httpx.AsyncClient = lambda timeout: fake_client
        dc_module.DemucsClient.POLL_INTERVAL_SECONDS = 0
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        with pytest.raises(asyncio.CancelledError):
            await client.separate_vocals(src, cancel_event=cancel_event)
    finally:
        dc_module.httpx.AsyncClient = original_client
        dc_module.DemucsClient.POLL_INTERVAL_SECONDS = original_poll_interval

    assert fake_client.deleted == ["http://127.0.0.1:8001/jobs/job-cancel"]


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


def test_demucs_client_preload_whisperx_models_posts_request_and_parses_response(tmp_path):
    """Demucs client should trigger remote WhisperX preload and parse the response."""

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "requested_models": "transcription=tiny,align=en,fr",
                "device": "cpu",
                "compute_type": None,
                "loaded_entries": ["transcription=tiny", "align=en", "align=fr"],
                "detail": "Preloaded 3 WhisperX model entries",
            }

    seen = {}

    def fake_post(url, data, timeout):
        seen["url"] = url
        seen["data"] = data
        seen["timeout"] = timeout
        return FakeResponse()

    with patch("services.demucs_client.httpx.post", side_effect=fake_post):
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        result = client.preload_whisperx_models(
            whisperx_preload_models="transcription=tiny,align=en,fr",
            device="cpu",
        )

    assert seen["url"] == "http://127.0.0.1:8001/whisperx/preload"
    assert seen["data"]["whisperx_preload_models"] == "transcription=tiny,align=en,fr"
    assert seen["data"]["device"] == "cpu"
    assert seen["timeout"] == DemucsClient.PRELOAD_TIMEOUT_SECONDS
    assert result.requested_models == "transcription=tiny,align=en,fr"
    assert result.loaded_entries == ["transcription=tiny", "align=en", "align=fr"]
    assert result.detail == "Preloaded 3 WhisperX model entries"


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
    assert result.demucs_direct_media_max_mb == settings.demucs_direct_media_max_mb
    assert result.whisperx_transcription_model == settings.whisperx_transcription_model
    assert result.whisperx_align_language == settings.whisperx_align_language
    assert result.whisperx_detect_language == settings.whisperx_detect_language
    assert result.whisperx_use_synced_lyrics == settings.whisperx_use_synced_lyrics
    assert result.whisperx_preload_models == settings.whisperx_preload_models


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


def test_runtime_settings_preload_whisperx_models_uses_current_settings():
    """Runtime settings service should forward the configured preload list to Demucs."""
    service = RuntimeSettingsService()
    original_demucs_device = settings.demucs_device
    original_demucs_api_url = settings.demucs_api_url
    try:
        settings.demucs_device = "cpu"
        settings.demucs_api_url = "http://127.0.0.1:8001"
        with patch(
            "services.runtime_settings_service.DemucsClient.preload_whisperx_models",
            return_value={
                "requested_models": "transcription=tiny,align=en,fr",
                "device": "cpu",
                "compute_type": None,
                "loaded_entries": ["transcription=tiny", "align=en", "align=fr"],
                "detail": "Preloaded 3 WhisperX model entries",
            },
        ) as mock_preload:
            result = service.preload_whisperx_models("transcription=tiny,align=en,fr")

        mock_preload.assert_called_once_with(
            whisperx_preload_models="transcription=tiny,align=en,fr",
            device="cpu",
        )
        assert result["requested_models"] == "transcription=tiny,align=en,fr"
        assert result["loaded_entries"] == ["transcription=tiny", "align=en", "align=fr"]
    finally:
        settings.demucs_device = original_demucs_device
        settings.demucs_api_url = original_demucs_api_url


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
    original_cutoff = settings.demucs_direct_media_max_mb
    original_whisperx_transcription_model = settings.whisperx_transcription_model
    original_whisperx_align_language = settings.whisperx_align_language
    original_whisperx_detect_language = settings.whisperx_detect_language
    original_whisperx_use_synced_lyrics = settings.whisperx_use_synced_lyrics
    original_whisperx_preload_models = settings.whisperx_preload_models
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
                    demucs_direct_media_max_mb=750,
                    whisperx_transcription_model="base",
                    whisperx_align_language="en",
                    whisperx_detect_language=True,
                    whisperx_use_synced_lyrics=True,
                    whisperx_preload_models="transcription=tiny,align=en,align=zh",
                )
            )
        assert result.demucs_model == "htdemucs_ft"
        assert result.demucs_device == "cpu"
        assert result.demucs_output_format == "mp3"
        assert result.demucs_mp3_bitrate == 256
        assert result.demucs_direct_media_max_mb == 750
        assert result.whisperx_transcription_model == "base"
        assert result.whisperx_align_language == "en"
        assert result.whisperx_detect_language is True
        assert result.whisperx_use_synced_lyrics is True
        assert result.whisperx_preload_models == "transcription=tiny,align=en,align=zh"
    finally:
        settings.demucs_model = original_model
        settings.demucs_device = original_device
        settings.demucs_output_format = original_output
        settings.demucs_mp3_bitrate = original_bitrate
        settings.demucs_direct_media_max_mb = original_cutoff
        settings.whisperx_transcription_model = original_whisperx_transcription_model
        settings.whisperx_align_language = original_whisperx_align_language
        settings.whisperx_detect_language = original_whisperx_detect_language
        settings.whisperx_use_synced_lyrics = original_whisperx_use_synced_lyrics
        settings.whisperx_preload_models = original_whisperx_preload_models


def test_runtime_settings_update_settings_rejects_invalid_demucs_fields():
    """Runtime settings should validate demucs advanced fields."""
    service = RuntimeSettingsService()
    with pytest.raises(ValueError, match="demucs_device"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_device="gpu"))
    with pytest.raises(ValueError, match="demucs_output_format"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_output_format="flac"))
    with pytest.raises(ValueError, match="demucs_mp3_bitrate"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_mp3_bitrate=32))
    with pytest.raises(ValueError, match="demucs_direct_media_max_mb"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_direct_media_max_mb=-1))
    with pytest.raises(ValueError, match="demucs_direct_media_max_mb"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_direct_media_max_mb=5001))
    with pytest.raises(ValueError, match="whisperx_transcription_model"):
        service.update_settings(RuntimeSettingsUpdateRequest(whisperx_transcription_model=" "))


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


def test_runtime_settings_update_settings_accepts_video_resolution():
    """Runtime settings should accept yt-dlp video resolution caps."""
    service = RuntimeSettingsService()
    original_resolution = settings.ytdlp_video_resolution
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
                RuntimeSettingsUpdateRequest(ytdlp_video_resolution="720")
            )
        assert result.ytdlp_video_resolution == "720"
    finally:
        settings.ytdlp_video_resolution = original_resolution


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


def test_runtime_settings_update_settings_rejects_invalid_video_resolution():
    """Runtime settings should reject unsupported yt-dlp video resolutions."""
    service = RuntimeSettingsService()
    with pytest.raises(ValueError, match="ytdlp_video_resolution"):
        service.update_settings(RuntimeSettingsUpdateRequest(ytdlp_video_resolution="999"))


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


def test_runtime_settings_update_settings_accepts_lyrics_provider_toggles():
    """Runtime settings should accept lyrics provider enable/disable updates."""
    service = RuntimeSettingsService()
    original_netease = settings.lyrics_provider_netease_enabled
    original_lrclib = settings.lyrics_provider_lrclib_enabled
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
                    lyrics_provider_netease_enabled=False,
                    lyrics_provider_lrclib_enabled=True,
                )
            )
        assert result.lyrics_provider_netease_enabled is False
        assert result.lyrics_provider_lrclib_enabled is True
    finally:
        settings.lyrics_provider_netease_enabled = original_netease
        settings.lyrics_provider_lrclib_enabled = original_lrclib


def test_runtime_settings_update_settings_persists_to_database(db_session):
    """Updating settings with a DB session should persist selected values."""
    service = RuntimeSettingsService()
    original_stage_qr_url = settings.stage_qr_url
    original_stage_lobby_media_path = settings.stage_lobby_media_path
    original_concurrent = settings.concurrent_ytdlp_search_enabled
    original_netease = settings.lyrics_provider_netease_enabled
    original_lrclib = settings.lyrics_provider_lrclib_enabled
    original_resolution = settings.ytdlp_video_resolution
    original_cutoff = settings.demucs_direct_media_max_mb
    original_whisperx_transcription_model = settings.whisperx_transcription_model
    original_whisperx_align_language = settings.whisperx_align_language
    original_whisperx_detect_language = settings.whisperx_detect_language
    original_whisperx_use_synced_lyrics = settings.whisperx_use_synced_lyrics
    original_whisperx_preload_models = settings.whisperx_preload_models
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
                    lyrics_provider_netease_enabled=False,
                    lyrics_provider_lrclib_enabled=True,
                    ytdlp_video_resolution="1080",
                    demucs_direct_media_max_mb=1234,
                    whisperx_transcription_model="tiny",
                    whisperx_align_language="",
                    whisperx_detect_language=False,
                    whisperx_use_synced_lyrics=True,
                    whisperx_preload_models="transcription=tiny",
                    stage_qr_url="https://karaoke.test/stage",
                    stage_lobby_media_path="/media/stage-lobby.mp4",
                ),
                db_session,
            )

        assert result.concurrent_ytdlp_search_enabled is True
        assert result.lyrics_provider_netease_enabled is False
        assert result.lyrics_provider_lrclib_enabled is True
        assert result.ytdlp_video_resolution == "1080"
        assert result.demucs_direct_media_max_mb == 1234
        assert result.whisperx_transcription_model == "tiny"
        assert result.whisperx_align_language == ""
        assert result.whisperx_detect_language is False
        assert result.whisperx_use_synced_lyrics is True
        assert result.whisperx_preload_models == "transcription=tiny"
        assert result.stage_qr_url == "https://karaoke.test/stage"
        assert result.stage_lobby_media_path == "/media/stage-lobby.mp4"

        stored = {
            row.key: row.value
            for row in db_session.query(RuntimeSetting).all()
        }
        assert stored["concurrent_ytdlp_search_enabled"] == "true"
        assert stored["lyrics_provider_netease_enabled"] == "false"
        assert stored["lyrics_provider_lrclib_enabled"] == "true"
        assert stored["ytdlp_video_resolution"] == "1080"
        assert stored["demucs_direct_media_max_mb"] == "1234"
        assert stored["whisperx_transcription_model"] == "tiny"
        assert stored["whisperx_align_language"] == ""
        assert stored["whisperx_detect_language"] == "false"
        assert stored["whisperx_use_synced_lyrics"] == "true"
        assert stored["whisperx_preload_models"] == "transcription=tiny"
        assert stored["stage_qr_url"] == "https://karaoke.test/stage"
        assert stored["stage_lobby_media_path"] == "/media/stage-lobby.mp4"
    finally:
        settings.stage_qr_url = original_stage_qr_url
        settings.stage_lobby_media_path = original_stage_lobby_media_path
        settings.concurrent_ytdlp_search_enabled = original_concurrent
        settings.lyrics_provider_netease_enabled = original_netease
        settings.lyrics_provider_lrclib_enabled = original_lrclib
        settings.ytdlp_video_resolution = original_resolution
        settings.demucs_direct_media_max_mb = original_cutoff
        settings.whisperx_transcription_model = original_whisperx_transcription_model
        settings.whisperx_align_language = original_whisperx_align_language
        settings.whisperx_detect_language = original_whisperx_detect_language
        settings.whisperx_use_synced_lyrics = original_whisperx_use_synced_lyrics
        settings.whisperx_preload_models = original_whisperx_preload_models


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
                RuntimeSetting(key="stage_lobby_media_path", value="/media/stage-lobby.mp4"),
                RuntimeSetting(key="ffmpeg_preset", value="veryslow"),
                RuntimeSetting(key="ytdlp_video_resolution", value="720"),
                RuntimeSetting(key="demucs_direct_media_max_mb", value="777"),
                RuntimeSetting(key="whisperx_transcription_model", value="base"),
                RuntimeSetting(key="whisperx_align_language", value="zh"),
                RuntimeSetting(key="whisperx_detect_language", value="true"),
                RuntimeSetting(key="whisperx_use_synced_lyrics", value="false"),
                RuntimeSetting(key="whisperx_preload_models", value="transcription=base,align=zh"),
            ]
        )
        db_session.commit()

        settings.demucs_model = "temporary-model"
        settings.stage_qr_url = ""
        settings.stage_lobby_media_path = ""
        settings.ytdlp_video_resolution = "default"
        settings.demucs_direct_media_max_mb = 500
        settings.whisperx_transcription_model = "tiny"
        settings.whisperx_align_language = "en"
        settings.whisperx_detect_language = False
        settings.whisperx_use_synced_lyrics = False
        settings.whisperx_preload_models = "transcription=tiny,align=en"

        applied = service.load_persisted_settings(db_session)

        assert "demucs_model" in applied
        assert "stage_qr_url" in applied
        assert "stage_lobby_media_path" in applied
        assert "ytdlp_video_resolution" in applied
        assert "demucs_direct_media_max_mb" in applied
        assert settings.demucs_model == "persisted-model"
        assert settings.stage_qr_url == "https://karaoke.test/stage"
        assert settings.stage_lobby_media_path == "/media/stage-lobby.mp4"
        assert settings.ytdlp_video_resolution == "720"
        assert settings.demucs_direct_media_max_mb == 777
        assert settings.whisperx_transcription_model == "base"
        assert settings.whisperx_align_language == "zh"
        assert settings.whisperx_detect_language is True
        assert settings.whisperx_use_synced_lyrics is False
        assert settings.whisperx_preload_models == "transcription=base,align=zh"

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


def test_stage_lobby_service_uses_configured_media_when_present(tmp_path):
    """Configured lobby media URL should be used when the file exists."""
    service = StageLobbyService()
    original_media = settings.media_path
    original_lobby = settings.stage_lobby_media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        lobby_file = settings.media_path / "custom-lobby.mp4"
        lobby_file.write_text("lobby", encoding="utf-8")
        settings.stage_lobby_media_path = "/media/custom-lobby.mp4"

        resolved = service.resolve_lobby_media_url()
        assert resolved == "/media/custom-lobby.mp4"
    finally:
        settings.media_path = original_media
        settings.stage_lobby_media_path = original_lobby


def test_stage_lobby_service_generates_fallback_when_missing(tmp_path):
    """Missing configured lobby media should trigger fallback generation path."""
    service = StageLobbyService()
    original_media = settings.media_path
    original_lobby = settings.stage_lobby_media_path
    try:
        settings.media_path = tmp_path / "media"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.stage_lobby_media_path = "/media/missing-lobby.mp4"

        fallback = settings.media_path / service.FALLBACK_FILE_NAME

        def _fake_run(*_, **__):
            fallback.write_text("generated", encoding="utf-8")
            return Mock(returncode=0)

        with patch("services.stage_lobby_service.subprocess.run", side_effect=_fake_run) as mock_run:
            resolved = service.resolve_lobby_media_url()

        assert resolved == f"/media/{service.FALLBACK_FILE_NAME}"
        assert fallback.exists()
        assert mock_run.called
    finally:
        settings.media_path = original_media
        settings.stage_lobby_media_path = original_lobby
