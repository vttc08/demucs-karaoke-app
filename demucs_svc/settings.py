from datetime import timedelta
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


SERVICE_ROOT = Path(__file__).resolve().parent
ENV_FILE = Path(os.getenv("DEMUCS_ENV_FILE", str(SERVICE_ROOT / ".env"))).expanduser()
DEFAULT_IO_ROOT = SERVICE_ROOT / "io"


class DemucsSettings(BaseSettings):
    """Demucs service settings loaded from the service-local environment."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    io_root: Path = Field(default=DEFAULT_IO_ROOT, validation_alias="DEMUCS_IO_ROOT")
    api_key: str = Field(default="", validation_alias="DEMUCS_API_KEY")
    demucs_model: str = "htdemucs"
    demucs_device: str = "cuda"
    demucs_output_format: str = "wav"
    demucs_mp3_bitrate: int = 320
    whisperx_transcription_model: str = "tiny"
    whisperx_align_language: str = "en"
    whisperx_detect_language: bool = False
    whisperx_use_synced_lyrics: bool = False
    whisperx_preload_models: str = "transcription=tiny,align=en"
    demucs_gc_interval_seconds: float = 600.0
    demucs_gc_low_free_vram_bytes: int = 2 * 1024 * 1024 * 1024

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.io_root = self._resolve_io_root(self.io_root)

    @staticmethod
    def _resolve_io_root(value: Path) -> Path:
        resolved = Path(value).expanduser()
        if not resolved.is_absolute():
            resolved = SERVICE_ROOT / resolved
        return resolved.resolve()


settings = DemucsSettings()

IO_ROOT = settings.io_root
INCOMING_ROOT = IO_ROOT / "incoming"
OUTPUT_ROOT = IO_ROOT / "output"

DEFAULT_DEMUCS_MODEL = settings.demucs_model
DEFAULT_DEMUCS_DEVICE = settings.demucs_device
DEFAULT_OUTPUT_FORMAT = settings.demucs_output_format
DEFAULT_MP3_BITRATE = settings.demucs_mp3_bitrate
DEFAULT_WHISPERX_TRANSCRIPTION_MODEL = settings.whisperx_transcription_model
DEFAULT_WHISPERX_ALIGN_LANGUAGE = settings.whisperx_align_language
DEFAULT_WHISPERX_DETECT_LANGUAGE = settings.whisperx_detect_language
DEFAULT_WHISPERX_USE_SYNCED_LYRICS = settings.whisperx_use_synced_lyrics
DEFAULT_WHISPERX_PRELOAD_MODELS = settings.whisperx_preload_models
JOB_RETENTION_SECONDS = int(timedelta(minutes=30).total_seconds())
JOB_OUTPUT_TAIL_LINES = 120
DEMUCS_GC_INTERVAL_SECONDS = settings.demucs_gc_interval_seconds
DEMUCS_GC_LOW_FREE_VRAM_BYTES = settings.demucs_gc_low_free_vram_bytes

INCOMING_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
