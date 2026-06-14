from .common import *



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
