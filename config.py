"""Application configuration."""
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Media paths
    media_path: Path = Path("/tmp/karaoke_media")
    cache_path: Path = Path("/tmp/karaoke_cache")

    # External services
    demucs_api_url: str = "http://localhost:8001"

    # Database
    database_url: str = "sqlite:///./karaoke.db"

    # External tools (will be resolved to full paths)
    ytdlp_path: str = "yt-dlp"
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Resolve executable paths on initialization
        self.ytdlp_path = find_executable(self.ytdlp_path.split('/')[-1])
        self.ffmpeg_path = find_executable(self.ffmpeg_path.split('/')[-1])

    def ensure_paths(self):
        """Create required directories if they don't exist."""
        self.media_path.mkdir(parents=True, exist_ok=True)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
