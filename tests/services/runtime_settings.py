import os
from .common import *

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


def test_demucs_client_trigger_garbage_collection_posts_request_and_parses_response():
    """Demucs client should trigger remote garbage collection and parse the response."""

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "requested_mode": "adaptive",
                "executed_mode": "full",
                "triggered_by": "manual",
                "detail": "Released WhisperX caches and CUDA memory",
                "active_job_count": 0,
                "running_job_count": 0,
                "free_vram_bytes": 1024,
                "total_vram_bytes": 2048,
                "python_gc_collected": 9,
                "whisperx_unloaded": {"transcription_models": 1, "align_models": 1},
                "cuda_cache_cleared": True,
                "cuda_ipc_cleared": True,
                "started_at": "2026-06-14T00:00:00+00:00",
                "finished_at": "2026-06-14T00:00:00.100000+00:00",
            }

    seen = {}

    def fake_post(url, params, timeout):
        seen["url"] = url
        seen["params"] = params
        seen["timeout"] = timeout
        return FakeResponse()

    with patch("services.demucs_client.httpx.post", side_effect=fake_post):
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        result = client.trigger_garbage_collection(mode="adaptive")

    assert seen["url"] == "http://127.0.0.1:8001/gc"
    assert seen["params"] == {"mode": "adaptive"}
    assert seen["timeout"] == DemucsClient.GC_TIMEOUT_SECONDS
    assert result.executed_mode == "full"
    assert result.whisperx_unloaded == {"transcription_models": 1, "align_models": 1}


def test_demucs_client_delete_job_artifacts_uses_artifact_endpoint():
    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

    seen = {}

    def fake_delete(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return FakeResponse()

    with patch("services.demucs_client.httpx.delete", side_effect=fake_delete):
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        client.delete_job_artifacts("job-123")

    assert seen["url"] == "http://127.0.0.1:8001/jobs/job-123/artifacts"
    assert seen["timeout"] == DemucsClient.DELETE_TIMEOUT_SECONDS


def test_demucs_client_get_io_usage_uses_io_endpoint():
    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "io_root": "/opt/karaoke/karaoke_svc/io",
                "incoming_root": "/opt/karaoke/karaoke_svc/io/incoming",
                "output_root": "/opt/karaoke/karaoke_svc/io/output",
                "total_bytes": 1024,
                "incoming_bytes": 256,
                "output_bytes": 768,
                "total_files": 4,
                "incoming_files": 1,
                "output_files": 3,
                "active_job_count": 0,
                "running_job_count": 0,
                "terminal_job_count": 2,
                "detail": "Current Demucs IO footprint",
            }

    seen = {}

    def fake_get(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return FakeResponse()

    with patch("services.demucs_client.httpx.get", side_effect=fake_get):
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        result = client.get_io_usage()

    assert seen["url"] == "http://127.0.0.1:8001/io"
    assert seen["timeout"] == DemucsClient.IO_TIMEOUT_SECONDS
    assert result.total_bytes == 1024
    assert result.terminal_job_count == 2


def test_demucs_client_cleanup_io_uses_io_endpoint():
    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "io_root": "/opt/karaoke/karaoke_svc/io",
                "deleted_bytes": 1024,
                "deleted_files": 4,
                "deleted_job_count": 2,
                "active_job_count": 0,
                "running_job_count": 0,
                "detail": "Deleted Demucs IO scratch files",
            }

    seen = {}

    def fake_delete(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return FakeResponse()

    with patch("services.demucs_client.httpx.delete", side_effect=fake_delete):
        client = DemucsClient(api_url="http://127.0.0.1:8001")
        result = client.cleanup_io()

    assert seen["url"] == "http://127.0.0.1:8001/io"
    assert seen["timeout"] == DemucsClient.IO_CLEANUP_TIMEOUT_SECONDS
    assert result.deleted_job_count == 2
    assert result.deleted_bytes == 1024

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
    assert result.demucs_poll_interval_seconds == settings.demucs_poll_interval_seconds
    assert result.whisperx_transcription_model == settings.whisperx_transcription_model
    assert result.whisperx_align_language == settings.whisperx_align_language
    assert result.whisperx_detect_language == settings.whisperx_detect_language
    assert result.whisperx_use_synced_lyrics == settings.whisperx_use_synced_lyrics
    assert result.whisperx_preload_models == settings.whisperx_preload_models
    assert result.stage_vocals_volume_default == settings.stage_vocals_volume_default

def test_connection_manager_uses_configured_default_vocals_volume():
    """Stage state should seed vocals volume from the configured default."""
    original_default = settings.stage_vocals_volume_default
    try:
        settings.stage_vocals_volume_default = 0.35
        manager = ConnectionManager()
        assert manager.get_stage_state()["vocals_volume"] == 0.35
    finally:
        settings.stage_vocals_volume_default = original_default

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

def test_runtime_settings_get_proxy_info_uses_configured_proxy():
    """Proxy info lookup should route through the configured proxy URL."""
    service = RuntimeSettingsService()
    original_proxy = settings.ytdlp_proxy_url
    try:
        settings.ytdlp_proxy_url = "socks5://127.0.0.1:1080"

        class FakeResponse:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {
                    "ip": "192.168.0.1",
                    "org": "AS123 Home Communications Inc.",
                    "city": "Home",
                    "country": "CA",
                }

        seen = {}

        def fake_get(url, timeout, proxy):
            seen["url"] = url
            seen["timeout"] = timeout
            seen["proxy"] = proxy
            return FakeResponse()

        with patch("services.runtime_settings_service.httpx.get", side_effect=fake_get):
            result = service.get_proxy_info()

        assert seen["url"] == "https://ipinfo.io/json"
        assert seen["timeout"] == service.PROXY_INFO_TIMEOUT_SECONDS
        assert seen["proxy"] == "socks5://127.0.0.1:1080"
        assert result.ip == "192.168.0.1"
        assert result.org == "AS123 Home Communications Inc."
        assert result.city == "Home"
        assert result.country == "CA"
    finally:
        settings.ytdlp_proxy_url = original_proxy

def test_runtime_settings_get_storage_usage_estimates_file_sizes_and_sqlite_db(tmp_path):
    """Storage usage should sum directory trees and a file-backed SQLite db."""
    service = RuntimeSettingsService()
    media_dir = tmp_path / "media"
    cache_dir = tmp_path / "cache"
    database_path = tmp_path / "karaoke.db"
    media_dir.mkdir()
    cache_dir.mkdir()
    (media_dir / "song.mp4").write_bytes(b"a" * 10)
    nested_dir = media_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "artwork.png").write_bytes(b"b" * 4)
    (cache_dir / "working.tmp").write_bytes(b"c" * 7)
    database_path.write_bytes(b"dbdata")

    original_media = settings.media_path
    original_cache = settings.cache_path
    original_database_url = settings.database_url
    try:
        settings.media_path = media_dir
        settings.cache_path = cache_dir
        settings.database_url = f"sqlite:///{database_path}"

        usage = service.get_storage_usage()
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
        settings.database_url = original_database_url

    assert usage.media_bytes == 14
    assert usage.cache_bytes == 7
    assert usage.database_available is True
    assert usage.database_bytes == 6
    assert usage.total_bytes == 27
    assert usage.media_display == "14 B"
    assert usage.cache_display == "7 B"
    assert usage.database_display == "6 B"
    assert usage.total_display == "27 B"

def test_runtime_settings_get_storage_usage_handles_missing_media_and_non_sqlite_db(tmp_path):
    """Storage usage should tolerate missing paths and skip non-SQLite dbs."""
    service = RuntimeSettingsService()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "working.tmp").write_bytes(b"hello")

    original_media = settings.media_path
    original_cache = settings.cache_path
    original_database_url = settings.database_url
    try:
        settings.media_path = tmp_path / "missing-media"
        settings.cache_path = cache_dir
        settings.database_url = "postgresql://user:pass@localhost/karaoke"

        usage = service.get_storage_usage()
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
        settings.database_url = original_database_url

    assert usage.media_bytes == 0
    assert usage.cache_bytes == 5
    assert usage.database_available is False
    assert usage.database_bytes is None
    assert usage.total_bytes == 5

def test_runtime_settings_get_storage_usage_skips_unreadable_directory(tmp_path):
    """Unreadable directories should not fail the storage usage probe."""
    service = RuntimeSettingsService()
    media_dir = tmp_path / "media"
    cache_dir = tmp_path / "cache"
    media_dir.mkdir()
    cache_dir.mkdir()
    (media_dir / "song.mp4").write_bytes(b"a" * 10)
    (cache_dir / "working.tmp").write_bytes(b"b" * 8)

    original_media = settings.media_path
    original_cache = settings.cache_path
    original_database_url = settings.database_url
    original_scandir = os.scandir
    try:
        settings.media_path = media_dir
        settings.cache_path = cache_dir
        settings.database_url = "sqlite:///./temporary-storage-probe.db"

        def fake_scandir(path):
            if Path(path) == media_dir:
                raise PermissionError("denied")
            return original_scandir(path)

        with patch("services.runtime_settings_service.os.scandir", side_effect=fake_scandir):
            usage = service.get_storage_usage()
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache
        settings.database_url = original_database_url

    assert usage.media_bytes == 0
    assert usage.cache_bytes == 8
    assert usage.database_available is True

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
    original_poll_interval_seconds = settings.demucs_poll_interval_seconds
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
                    demucs_poll_interval_seconds=2.5,
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
        assert result.demucs_poll_interval_seconds == 2.5
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
        settings.demucs_poll_interval_seconds = original_poll_interval_seconds
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
    with pytest.raises(ValueError, match="demucs_poll_interval_seconds"):
        service.update_settings(RuntimeSettingsUpdateRequest(demucs_poll_interval_seconds=0.1))
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
    original_stage_vocals_volume_default = settings.stage_vocals_volume_default
    original_concurrent = settings.concurrent_ytdlp_search_enabled
    original_netease = settings.lyrics_provider_netease_enabled
    original_lrclib = settings.lyrics_provider_lrclib_enabled
    original_resolution = settings.ytdlp_video_resolution
    original_cutoff = settings.demucs_direct_media_max_mb
    original_poll_interval_seconds = settings.demucs_poll_interval_seconds
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
                    demucs_poll_interval_seconds=1.75,
                    whisperx_transcription_model="tiny",
                    whisperx_align_language="",
                    whisperx_detect_language=False,
                    whisperx_use_synced_lyrics=True,
                    whisperx_preload_models="transcription=tiny",
                    stage_qr_url="https://karaoke.test/stage",
                    stage_lobby_media_path="/media/stage-lobby.mp4",
                    stage_vocals_volume_default=0.4,
                ),
                db_session,
            )

        assert result.concurrent_ytdlp_search_enabled is True
        assert result.lyrics_provider_netease_enabled is False
        assert result.lyrics_provider_lrclib_enabled is True
        assert result.ytdlp_video_resolution == "1080"
        assert result.demucs_direct_media_max_mb == 1234
        assert result.demucs_poll_interval_seconds == 1.75
        assert result.whisperx_transcription_model == "tiny"
        assert result.whisperx_align_language == ""
        assert result.whisperx_detect_language is False
        assert result.whisperx_use_synced_lyrics is True
        assert result.whisperx_preload_models == "transcription=tiny"
        assert result.stage_qr_url == "https://karaoke.test/stage"
        assert result.stage_lobby_media_path == "/media/stage-lobby.mp4"
        assert result.stage_vocals_volume_default == 0.4

        stored = {
            row.key: row.value
            for row in db_session.query(RuntimeSetting).all()
        }
        assert stored["concurrent_ytdlp_search_enabled"] == "true"
        assert stored["lyrics_provider_netease_enabled"] == "false"
        assert stored["lyrics_provider_lrclib_enabled"] == "true"
        assert stored["ytdlp_video_resolution"] == "1080"
        assert stored["demucs_direct_media_max_mb"] == "1234"
        assert stored["demucs_poll_interval_seconds"] == "1.75"
        assert stored["whisperx_transcription_model"] == "tiny"
        assert stored["whisperx_align_language"] == ""
        assert stored["whisperx_detect_language"] == "false"
        assert stored["whisperx_use_synced_lyrics"] == "true"
        assert stored["whisperx_preload_models"] == "transcription=tiny"
        assert stored["stage_qr_url"] == "https://karaoke.test/stage"
        assert stored["stage_lobby_media_path"] == "/media/stage-lobby.mp4"
        assert stored["stage_vocals_volume_default"] == "0.4"
    finally:
        settings.stage_qr_url = original_stage_qr_url
        settings.stage_lobby_media_path = original_stage_lobby_media_path
        settings.stage_vocals_volume_default = original_stage_vocals_volume_default
        settings.concurrent_ytdlp_search_enabled = original_concurrent
        settings.lyrics_provider_netease_enabled = original_netease
        settings.lyrics_provider_lrclib_enabled = original_lrclib
        settings.ytdlp_video_resolution = original_resolution
        settings.demucs_direct_media_max_mb = original_cutoff
        settings.demucs_poll_interval_seconds = original_poll_interval_seconds
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
                RuntimeSetting(key="stage_vocals_volume_default", value="0.35"),
                RuntimeSetting(key="ffmpeg_preset", value="veryslow"),
                RuntimeSetting(key="ytdlp_video_resolution", value="720"),
                RuntimeSetting(key="demucs_direct_media_max_mb", value="777"),
                RuntimeSetting(key="demucs_poll_interval_seconds", value="1.25"),
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
        settings.stage_vocals_volume_default = 1.0
        settings.ytdlp_video_resolution = "default"
        settings.demucs_direct_media_max_mb = 500
        settings.demucs_poll_interval_seconds = 1.0
        settings.whisperx_transcription_model = "tiny"
        settings.whisperx_align_language = "en"
        settings.whisperx_detect_language = False
        settings.whisperx_use_synced_lyrics = False
        settings.whisperx_preload_models = "transcription=tiny,align=en"

        applied = service.load_persisted_settings(db_session)

        assert "demucs_model" in applied
        assert "stage_qr_url" in applied
        assert "stage_lobby_media_path" in applied
        assert "stage_vocals_volume_default" in applied
        assert "ytdlp_video_resolution" in applied
        assert "demucs_direct_media_max_mb" in applied
        assert "demucs_poll_interval_seconds" in applied
        assert settings.demucs_model == "persisted-model"
        assert settings.stage_qr_url == "https://karaoke.test/stage"
        assert settings.stage_lobby_media_path == "/media/stage-lobby.mp4"
        assert settings.stage_vocals_volume_default == 0.35
        assert settings.ytdlp_video_resolution == "720"
        assert settings.demucs_direct_media_max_mb == 777
        assert settings.demucs_poll_interval_seconds == 1.25
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
