"""Application configuration."""
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_base_path(value: str | None) -> str:
    """Normalize an optional URL path prefix for reverse-proxy deployments."""
    raw = (value or "").strip()
    if raw in {"", "/"}:
        return ""
    if "?" in raw or "#" in raw or any(char.isspace() for char in raw):
        raise ValueError("KARAOKE_BASE_PATH must be a URL path without query, fragment, or spaces")
    if not raw.startswith("/"):
        raw = f"/{raw}"
    raw = raw.rstrip("/")
    parts = [part for part in raw.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("KARAOKE_BASE_PATH must not contain path traversal segments")
    if "//" in raw:
        raise ValueError("KARAOKE_BASE_PATH must not contain empty path segments")
    return raw


def find_executable(name: str) -> str:
    """
    Find executable, preferring venv version.
    
    Args:
        name: Executable name (e.g., 'yt-dlp')
    
    Returns:
        Path to executable
    """
    # Check venv first
    venv_bin = Path(sys.prefix) / "bin" / name
    if venv_bin.exists():
        return str(venv_bin)
    
    # Fallback to system PATH
    import shutil
    system_path = shutil.which(name)
    if system_path:
        return system_path
    
    # Last resort: return name and hope it's in PATH
    return name


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    karaoke_base_path: str = ""

    # Media paths
    media_path: Path = Path("/tmp/karaoke_media")
    cache_path: Path = Path("/tmp/karaoke_cache")

    # External services
    demucs_api_url: str = "http://localhost:8001"
    demucs_model: str = "htdemucs"
    demucs_device: str = "cuda"
    demucs_output_format: str = "wav"
    demucs_mp3_bitrate: int = 320
    demucs_direct_media_max_mb: int = 500
    demucs_poll_interval_seconds: float = 1.0
    whisperx_transcription_model: str = "tiny"
    whisperx_align_language: str = "en"
    whisperx_detect_language: bool = False
    whisperx_use_synced_lyrics: bool = False
    whisperx_preload_models: str = "transcription=tiny,align=en"
    lrclib_api_url: str = "https://lrclib.net"
    musixmatch_token: str = ""
    lastfm_api_key: str = ""

    # Database
    database_url: str = "sqlite:///./karaoke.db"

    # External tools (will be resolved to full paths)
    ytdlp_path: str = "yt-dlp"
    ytdlp_proxy_url: str = ""
    ytdlp_video_resolution: str = "default"
    concurrent_ytdlp_search_enabled: bool = False
    lyrics_provider_netease_enabled: bool = True
    lyrics_provider_lrclib_enabled: bool = True
    ffmpeg_path: str = "ffmpeg"
    ffmpeg_preset: str = "veryfast"
    ffmpeg_crf: int = 23

    # Logging
    log_level: str = "INFO"
    log_dir: Path = Path("./logs")
    log_file_name: str = "karaoke.log"
    log_max_bytes: int = 5_242_880  # 5 MB
    log_backup_count: int = 5
    log_format: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    log_to_file_in_reload: bool = False
    stage_qr_url: str = ""
    stage_lobby_media_path: str = ""
    stage_vocals_volume_default: float = 1.0
    
    # WebSocket
    ws_heartbeat_interval: int = 30

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.karaoke_base_path = normalize_base_path(self.karaoke_base_path)
        # Resolve executable paths on initialization
        self.ytdlp_path = find_executable(self.ytdlp_path.split('/')[-1])
        self.ffmpeg_path = find_executable(self.ffmpeg_path.split('/')[-1])

    def ensure_paths(self):
        """Create required directories if they don't exist."""
        self.media_path.mkdir(parents=True, exist_ok=True)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
EXPLICIT_SETTINGS_FIELDS = frozenset(settings.model_fields_set)
