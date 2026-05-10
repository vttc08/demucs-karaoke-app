"""Helpers for generated media thumbnails."""

from __future__ import annotations

import hashlib
import logging
import subprocess
import shutil
from pathlib import Path

from config import settings
from adapters.ffmpeg import FFmpegAdapter

logger = logging.getLogger(__name__)

_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"}


class MediaThumbnailService:
    """Create and manage cached thumbnails for local media files."""

    def __init__(self) -> None:
        self.ffmpeg = FFmpegAdapter()

    @staticmethod
    def thumbnail_path_for_media_file(media_file: Path) -> Path:
        """Return the cache path for a media file thumbnail."""
        digest = hashlib.sha1(str(media_file.resolve()).encode("utf-8")).hexdigest()[:16]
        return settings.cache_path / "media-thumbnails" / f"{digest}.jpg"

    @staticmethod
    def thumbnail_url_for_media_file(media_file: Path) -> str:
        """Return the public URL for a cached media thumbnail."""
        thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        relative_path = thumbnail_path.resolve().relative_to(settings.cache_path.resolve())
        return f"/cache/{relative_path.as_posix()}"

    def ensure_thumbnail_for_media_file(self, media_file: Path) -> Path | None:
        """Generate or refresh a cached thumbnail for a local media file."""
        media_kind = self._media_kind_for(media_file)
        if media_kind is None:
            return None

        thumbnail_path = self.thumbnail_path_for_media_file(media_file)
        if thumbnail_path.exists():
            try:
                if thumbnail_path.stat().st_mtime >= media_file.stat().st_mtime:
                    return thumbnail_path
            except FileNotFoundError:
                pass

        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if media_kind == "video":
                self.ffmpeg.extract_video_thumbnail(media_file, thumbnail_path)
            else:
                self.ffmpeg.extract_embedded_thumbnail(media_file, thumbnail_path)
        except (FileNotFoundError, shutil.Error, OSError, subprocess.CalledProcessError):
            logger.warning("Thumbnail generation failed media_file=%s thumbnail=%s", media_file, thumbnail_path)
            if thumbnail_path.exists():
                thumbnail_path.unlink()
            return None
        return thumbnail_path

    def remove_thumbnail_for_media_file(self, media_file: Path) -> bool:
        """Remove the cached thumbnail for a media file if it exists."""
        thumbnail_path = self.thumbnail_path_for_media_file(media_file)
        if not thumbnail_path.exists():
            return False
        thumbnail_path.unlink()
        return True

    def rename_thumbnail_for_media_file(self, source_media_file: Path, target_media_file: Path) -> bool:
        """Rename the cached thumbnail to match a moved media file."""
        source_thumbnail = self.thumbnail_path_for_media_file(source_media_file)
        if not source_thumbnail.exists():
            return False

        target_thumbnail = self.thumbnail_path_for_media_file(target_media_file)
        if source_thumbnail == target_thumbnail:
            return False

        target_thumbnail.parent.mkdir(parents=True, exist_ok=True)
        if target_thumbnail.exists():
            source_thumbnail.unlink()
            return True

        shutil.move(str(source_thumbnail), str(target_thumbnail))
        return True

    @staticmethod
    def _media_kind_for(media_file: Path) -> str | None:
        suffix = media_file.suffix.lower()
        if suffix in _VIDEO_EXTENSIONS:
            return "video"
        if suffix in _AUDIO_EXTENSIONS:
            return "audio"
        return None
