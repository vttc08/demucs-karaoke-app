"""Runtime settings service."""
from pathlib import Path

from config import find_executable, settings
from models import DemucsHealthResponse, RuntimeSettingsResponse, RuntimeSettingsUpdateRequest
from services.demucs_client import DemucsClient


class RuntimeSettingsService:
    """Manage runtime-editable settings and apply them in-process."""

    ALLOWED_FFMPEG_PRESETS = {
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    }

    def get_demucs_health(self) -> DemucsHealthResponse:
        """Return Demucs health for the current configured API URL."""
        return DemucsClient(api_url=settings.demucs_api_url).health_check()

    def _build_settings_response(
        self, demucs_health: DemucsHealthResponse | None
    ) -> RuntimeSettingsResponse:
        if demucs_health is None:
            demucs_healthy = False
            demucs_health_detail = "Health check pending"
        else:
            demucs_healthy = demucs_health.healthy
            demucs_health_detail = demucs_health.detail

        return RuntimeSettingsResponse(
            demucs_api_url=settings.demucs_api_url,
            demucs_healthy=demucs_healthy,
            demucs_health_detail=demucs_health_detail,
            ffmpeg_preset=settings.ffmpeg_preset,
            ffmpeg_crf=settings.ffmpeg_crf,
            ytdlp_path=settings.ytdlp_path,
            ffmpeg_path=settings.ffmpeg_path,
        )

    def get_settings(self) -> RuntimeSettingsResponse:
        """Return current runtime settings snapshot without blocking network calls."""
        return self._build_settings_response(demucs_health=None)

    def update_settings(
        self, payload: RuntimeSettingsUpdateRequest
    ) -> RuntimeSettingsResponse:
        """Apply validated runtime setting updates."""
        if payload.demucs_api_url is not None:
            value = payload.demucs_api_url.strip()
            if not value:
                raise ValueError("demucs_api_url cannot be empty")
            settings.demucs_api_url = value

        if payload.ffmpeg_preset is not None:
            preset = payload.ffmpeg_preset.strip().lower()
            if preset not in self.ALLOWED_FFMPEG_PRESETS:
                raise ValueError(
                    "ffmpeg_preset must be one of: "
                    + ", ".join(sorted(self.ALLOWED_FFMPEG_PRESETS))
                )
            settings.ffmpeg_preset = preset

        if payload.ffmpeg_crf is not None:
            crf = payload.ffmpeg_crf
            if crf < 0 or crf > 51:
                raise ValueError("ffmpeg_crf must be between 0 and 51")
            settings.ffmpeg_crf = crf

        if payload.ytdlp_path is not None:
            ytdlp_input = payload.ytdlp_path.strip()
            if not ytdlp_input:
                raise ValueError("ytdlp_path cannot be empty")
            settings.ytdlp_path = self._resolve_executable_path(ytdlp_input)

        if payload.ffmpeg_path is not None:
            ffmpeg_input = payload.ffmpeg_path.strip()
            if not ffmpeg_input:
                raise ValueError("ffmpeg_path cannot be empty")
            settings.ffmpeg_path = self._resolve_executable_path(ffmpeg_input)

        settings.ensure_paths()
        demucs_health = self.get_demucs_health()
        return self._build_settings_response(demucs_health=demucs_health)

    @staticmethod
    def _resolve_executable_path(value: str) -> str:
        """Resolve executable name/path similar to startup behavior."""
        candidate = Path(value)
        if candidate.exists():
            return str(candidate)
        return find_executable(value.split("/")[-1])
