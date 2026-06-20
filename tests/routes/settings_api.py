from .common import *



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
    assert "demucs_direct_media_max_mb" in data
    assert "demucs_poll_interval_seconds" in data
    assert "whisperx_transcription_model" in data
    assert "whisperx_align_language" in data
    assert "whisperx_detect_language" in data
    assert "whisperx_use_synced_lyrics" in data
    assert "whisperx_preload_models" in data
    assert "ffmpeg_preset" in data
    assert "ffmpeg_crf" in data
    assert "ytdlp_path" in data
    assert "ytdlp_proxy_url" in data
    assert "ytdlp_video_resolution" in data
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
            "demucs_direct_media_max_mb": 750,
            "demucs_poll_interval_seconds": 2.5,
            "whisperx_transcription_model": "base",
            "whisperx_align_language": "en",
            "whisperx_detect_language": True,
            "whisperx_use_synced_lyrics": True,
            "whisperx_preload_models": "transcription=tiny,align=en,align=zh",
            "ffmpeg_preset": "superfast",
            "ffmpeg_crf": 28,
            "media_path": "/tmp/karaoke_media_test",
            "cache_path": "/tmp/karaoke_cache_test",
            "ytdlp_path": "yt-dlp",
            "ytdlp_proxy_url": "socks5://127.0.0.1:1080",
            "ytdlp_video_resolution": "720",
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
    assert data["demucs_direct_media_max_mb"] == 750
    assert data["demucs_poll_interval_seconds"] == 2.5
    assert data["whisperx_transcription_model"] == "base"
    assert data["whisperx_align_language"] == "en"
    assert data["whisperx_detect_language"] is True
    assert data["whisperx_use_synced_lyrics"] is True
    assert data["whisperx_preload_models"] == "transcription=tiny,align=en,align=zh"
    assert data["ffmpeg_preset"] == "superfast"
    assert data["ffmpeg_crf"] == 28
    assert data["media_path"] == "/tmp/karaoke_media_test"
    assert data["cache_path"] == "/tmp/karaoke_cache_test"
    assert data["ytdlp_proxy_url"] == "socks5://127.0.0.1:1080"
    assert data["ytdlp_video_resolution"] == "720"
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
                "whisperx_transcription_model": "tiny",
                "whisperx_align_language": "",
                "whisperx_detect_language": False,
                "whisperx_use_synced_lyrics": False,
                "whisperx_preload_models": "transcription=tiny",
                "ytdlp_video_resolution": "1080",
                "concurrent_ytdlp_search_enabled": True,
                "demucs_direct_media_max_mb": 333,
                "demucs_poll_interval_seconds": 1.25,
            },
        )
    assert response.status_code == 200

    db = TestingSessionLocal()
    try:
        stage_qr = db.query(RuntimeSetting).filter(RuntimeSetting.key == "stage_qr_url").first()
        stage_lobby = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "stage_lobby_media_path"
        ).first()
        resolution = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "ytdlp_video_resolution"
        ).first()
        cutoff = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "demucs_direct_media_max_mb"
        ).first()
        poll_interval = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "demucs_poll_interval_seconds"
        ).first()
        concurrent = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "concurrent_ytdlp_search_enabled"
        ).first()
        whisperx_transcription_model = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "whisperx_transcription_model"
        ).first()
        whisperx_align_language = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "whisperx_align_language"
        ).first()
        whisperx_detect_language = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "whisperx_detect_language"
        ).first()
        whisperx_use_synced_lyrics = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "whisperx_use_synced_lyrics"
        ).first()
        whisperx_preload_models = db.query(RuntimeSetting).filter(
            RuntimeSetting.key == "whisperx_preload_models"
        ).first()
        assert stage_qr is not None
        assert stage_qr.value == "https://karaoke.test/queue"
        assert stage_lobby is not None
        assert stage_lobby.value == "/media/stage-lobby.mp4"
        assert resolution is not None
        assert resolution.value == "1080"
        assert cutoff is not None
        assert cutoff.value == "333"
        assert poll_interval is not None
        assert poll_interval.value == "1.25"
        assert concurrent is not None
        assert concurrent.value == "true"
        assert whisperx_transcription_model is not None
        assert whisperx_transcription_model.value == "tiny"
        assert whisperx_align_language is not None
        assert whisperx_align_language.value == ""
        assert whisperx_detect_language is not None
        assert whisperx_detect_language.value == "false"
        assert whisperx_use_synced_lyrics is not None
        assert whisperx_use_synced_lyrics.value == "false"
        assert whisperx_preload_models is not None
        assert whisperx_preload_models.value == "transcription=tiny"
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

def test_get_proxy_info(client):
    """Proxy info endpoint should return proxy egress details."""
    authenticate_admin_client(client)
    with patch(
        "routes.settings.runtime_settings_service.get_proxy_info",
        return_value={
            "ip": "192.168.0.1",
            "org": "AS123 Home Communications Inc.",
            "city": "Home",
            "country": "CA",
            "detail": "Proxy info lookup completed",
        },
    ):
        response = client.post(
            "/api/settings/proxy-info",
            json={"proxy_url": "socks5://127.0.0.1:1080"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["ip"] == "192.168.0.1"
    assert data["org"] == "AS123 Home Communications Inc."
    assert data["city"] == "Home"
    assert data["country"] == "CA"

def test_get_proxy_info_requires_admin(client):
    """Proxy info endpoint should reject guests."""
    response = client.post(
        "/api/settings/proxy-info",
        json={"proxy_url": "socks5://127.0.0.1:1080"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin session required"

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

def test_preload_whisperx_models(client):
    """WhisperX preload endpoint should proxy the remote preload request."""
    authenticate_admin_client(client)
    with patch(
        "routes.settings.runtime_settings_service.preload_whisperx_models",
        return_value={
            "requested_models": "transcription=tiny,align=en,fr",
            "device": "cuda",
            "compute_type": None,
            "loaded_entries": ["transcription=tiny", "align=en", "align=fr"],
            "detail": "Preloaded 3 WhisperX model entries",
        },
    ):
        response = client.post(
            "/api/settings/whisperx/preload",
            json={"whisperx_preload_models": "transcription=tiny,align=en,fr"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["requested_models"] == "transcription=tiny,align=en,fr"
    assert data["loaded_entries"] == ["transcription=tiny", "align=en", "align=fr"]

def test_preload_whisperx_models_error(client):
    """WhisperX preload endpoint should map runtime errors to 400."""
    authenticate_admin_client(client)
    with patch(
        "routes.settings.runtime_settings_service.preload_whisperx_models",
        side_effect=RuntimeError("WhisperX is not installed in this environment"),
    ):
        response = client.post(
            "/api/settings/whisperx/preload",
            json={"whisperx_preload_models": "transcription=tiny,align=en,fr"},
        )
    assert response.status_code == 400
    assert "WhisperX is not installed" in response.json()["detail"]

def test_trigger_demucs_gc(client):
    """Settings GC endpoint should proxy the remote Demucs cleanup request."""
    authenticate_admin_client(client)
    with patch(
        "routes.settings.runtime_settings_service.trigger_demucs_garbage_collection",
        return_value={
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
        },
    ):
        response = client.post("/api/settings/demucs/gc")
    assert response.status_code == 200
    data = response.json()
    assert data["executed_mode"] == "full"
    assert data["running_job_count"] == 0

def test_update_runtime_settings_rejects_invalid_crf(client):
    """Runtime settings endpoint should validate ffmpeg_crf."""
    authenticate_admin_client(client)
    response = client.patch("/api/settings/", json={"ffmpeg_crf": 60})
    assert response.status_code == 400
    assert "ffmpeg_crf" in response.json()["detail"]

def test_update_runtime_settings_rejects_invalid_ytdlp_resolution(client):
    """Runtime settings endpoint should validate yt-dlp video resolution caps."""
    authenticate_admin_client(client)
    response = client.patch("/api/settings/", json={"ytdlp_video_resolution": "999"})
    assert response.status_code == 400
    assert "ytdlp_video_resolution" in response.json()["detail"]

def test_update_runtime_settings_rejects_invalid_demucs_direct_media_cutoff(client):
    """Runtime settings endpoint should validate the direct-media cutoff."""
    authenticate_admin_client(client)
    response = client.patch("/api/settings/", json={"demucs_direct_media_max_mb": 5001})
    assert response.status_code == 400
    assert "demucs_direct_media_max_mb" in response.json()["detail"]
