"""Tests for API routes."""
import asyncio
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
    ProcessingTask,
    ProcessingTaskStatus,
    QueueItem,
    QueueStatus,
    RuntimeSetting,
)
from services import lyrics_service as lyrics_service_module
from services.auth_service import ADMIN_SESSION_COOKIE, AuthService
from services.i18n_service import LOCALE_COOKIE
from services.media_naming import build_media_stem
from services.media_thumbnail_service import MediaThumbnailService
from services.processing_task_service import processing_task_service
from services.task_stream_service import task_stream_manager
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
    original_demucs_direct_media_max_mb = settings.demucs_direct_media_max_mb
    original_whisperx_transcription_model = settings.whisperx_transcription_model
    original_whisperx_align_language = settings.whisperx_align_language
    original_whisperx_detect_language = settings.whisperx_detect_language
    original_whisperx_use_synced_lyrics = settings.whisperx_use_synced_lyrics
    original_whisperx_preload_models = settings.whisperx_preload_models
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
    with patch("routes.media_library.task_execution_coordinator.start"):
        yield TestClient(app)
    settings.demucs_api_url = original_demucs_api_url
    settings.demucs_model = original_demucs_model
    settings.demucs_device = original_demucs_device
    settings.demucs_output_format = original_demucs_output_format
    settings.demucs_mp3_bitrate = original_demucs_mp3_bitrate
    settings.demucs_direct_media_max_mb = original_demucs_direct_media_max_mb
    settings.whisperx_transcription_model = original_whisperx_transcription_model
    settings.whisperx_align_language = original_whisperx_align_language
    settings.whisperx_detect_language = original_whisperx_detect_language
    settings.whisperx_use_synced_lyrics = original_whisperx_use_synced_lyrics
    settings.whisperx_preload_models = original_whisperx_preload_models
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


def subscribe_websocket(websocket, page: str) -> None:
    """Register a websocket client role for targeted broadcasts."""
    websocket.send_json(
        {
            "type": "client_subscribe",
            "data": {"page": page},
            "timestamp": 123,
        }
    )


