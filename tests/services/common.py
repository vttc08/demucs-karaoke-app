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
    MediaFileDeleteConflictError,
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
    LyricsPreset,
    LyricsPresetCreateRequest,
    LyricsPresetUpdateRequest,
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


@pytest.fixture
def mock_ytdlp():
    """Patch the YouTube service's yt-dlp adapter constructor for focused tests."""
    with patch("services.youtube_service.YtDlpAdapter") as mock_adapter:
        yield mock_adapter
