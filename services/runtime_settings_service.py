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
    ALLOWED_DEMUCS_DEVICES = {"cuda", "cpu"}
    ALLOWED_DEMUCS_OUTPUT_FORMATS = {"wav", "mp3"}

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
            demucs_model=settings.demucs_model,
            demucs_device=settings.demucs_device,
            demucs_output_format=settings.demucs_output_format,
            demucs_mp3_bitrate=settings.demucs_mp3_bitrate,
            ffmpeg_preset=settings.ffmpeg_preset,
            ffmpeg_crf=settings.ffmpeg_crf,
            ytdlp_path=settings.ytdlp_path,
            ffmpeg_path=settings.ffmpeg_path,
            media_path=str(settings.media_path),
            cache_path=str(settings.cache_path),
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

        if payload.demucs_model is not None:
            model = payload.demucs_model.strip()
            if not model:
                raise ValueError("demucs_model cannot be empty")
            settings.demucs_model = model

        if payload.demucs_device is not None:
            device = payload.demucs_device.strip().lower()
            if device not in self.ALLOWED_DEMUCS_DEVICES:
                raise ValueError(
                    "demucs_device must be one of: "
                    + ", ".join(sorted(self.ALLOWED_DEMUCS_DEVICES))
                )
            settings.demucs_device = device

        if payload.demucs_output_format is not None:
            output_format = payload.demucs_output_format.strip().lower()
            if output_format not in self.ALLOWED_DEMUCS_OUTPUT_FORMATS:
                raise ValueError(
                    "demucs_output_format must be one of: "
                    + ", ".join(sorted(self.ALLOWED_DEMUCS_OUTPUT_FORMATS))
                )
            settings.demucs_output_format = output_format

        if payload.demucs_mp3_bitrate is not None:
            bitrate = payload.demucs_mp3_bitrate
            if bitrate < 64 or bitrate > 320:
                raise ValueError("demucs_mp3_bitrate must be between 64 and 320")
            settings.demucs_mp3_bitrate = bitrate

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

        if payload.media_path is not None:
            media_path_input = payload.media_path.strip()
            if not media_path_input:
                raise ValueError("media_path cannot be empty")
            settings.media_path = Path(media_path_input)

        if payload.cache_path is not None:
            cache_path_input = payload.cache_path.strip()
            if not cache_path_input:
                raise ValueError("cache_path cannot be empty")
            settings.cache_path = Path(cache_path_input)

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
