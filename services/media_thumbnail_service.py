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
_THUMBNAIL_SIDECAR_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


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
        """Return the public URL for the best thumbnail source."""
        thumbnail_path = MediaThumbnailService.best_thumbnail_path_for_media_file(media_file)
        if thumbnail_path is None:
            thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        return MediaThumbnailService.public_url_for_path(thumbnail_path)

    @staticmethod
    def public_url_for_path(file_path: Path) -> str:
        """Return a public URL for a media or cache file."""
        resolved = file_path.resolve()
        media_root = settings.media_path.resolve()
        cache_root = settings.cache_path.resolve()

        try:
            relative_path = resolved.relative_to(media_root)
            return f"/media/{relative_path.as_posix()}"
        except ValueError:
            pass

        try:
            relative_path = resolved.relative_to(cache_root)
            return f"/cache/{relative_path.as_posix()}"
        except ValueError as exc:
            raise ValueError(f"File path is outside media/cache roots: {file_path}") from exc

    @staticmethod
    def thumbnail_sidecar_path_for_media_file(media_file: Path, extension: str = ".jpg") -> Path:
        """Return the durable adjacent thumbnail path for a media file."""
        return media_file.with_suffix(extension)

    @staticmethod
    def adjacent_thumbnail_paths_for_media_file(media_file: Path) -> list[Path]:
        """Return candidate adjacent thumbnail sidecar paths in precedence order."""
        return [
            MediaThumbnailService.thumbnail_sidecar_path_for_media_file(media_file, extension)
            for extension in _THUMBNAIL_SIDECAR_EXTENSIONS
        ]

    @staticmethod
    def best_thumbnail_path_for_media_file(media_file: Path) -> Path | None:
        """Return the preferred existing thumbnail for a media file."""
        for candidate in MediaThumbnailService.adjacent_thumbnail_paths_for_media_file(media_file):
            if candidate.exists():
                return candidate

        thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        if thumbnail_path.exists():
            return thumbnail_path
        return None

    def ensure_thumbnail_for_media_file(self, media_file: Path) -> Path | None:
        """Generate or refresh a cached thumbnail for a local media file."""
        media_kind = self._media_kind_for(media_file)
        if media_kind is None:
            return None

        for candidate in self.adjacent_thumbnail_paths_for_media_file(media_file):
            if candidate.exists():
                return candidate

        if media_kind == "audio":
            adjacent_thumbnail = self.thumbnail_sidecar_path_for_media_file(media_file)
            cache_thumbnail = self.thumbnail_path_for_media_file(media_file)
            if cache_thumbnail.exists():
                adjacent_thumbnail.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(cache_thumbnail), str(adjacent_thumbnail))
                return adjacent_thumbnail
            try:
                self.ffmpeg.extract_embedded_thumbnail(media_file, adjacent_thumbnail)
            except (FileNotFoundError, shutil.Error, OSError, subprocess.CalledProcessError):
                logger.warning(
                    "Embedded thumbnail extraction failed media_file=%s thumbnail=%s",
                    media_file,
                    adjacent_thumbnail,
                )
                if adjacent_thumbnail.exists():
                    adjacent_thumbnail.unlink()
                return None
            return adjacent_thumbnail

        thumbnail_path = self.thumbnail_path_for_media_file(media_file)
        try:
            if thumbnail_path.exists() and thumbnail_path.stat().st_mtime >= media_file.stat().st_mtime:
                return thumbnail_path
        except FileNotFoundError:
            pass

        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.ffmpeg.extract_video_thumbnail(media_file, thumbnail_path)
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

    def remove_thumbnail_sidecars_for_media_file(self, media_file: Path) -> int:
        """Remove any adjacent thumbnail sidecars for a media file."""
        removed = 0
        for candidate in self.adjacent_thumbnail_paths_for_media_file(media_file):
            if not candidate.exists():
                continue
            candidate.unlink()
            removed += 1
        return removed

    def rename_thumbnail_for_media_file(self, source_media_file: Path, target_media_file: Path) -> bool:
        """Rename or promote thumbnails to match a moved media file."""
        renamed = self.rename_thumbnail_sidecars_for_media_file(source_media_file, target_media_file)

        source_thumbnail = self.thumbnail_path_for_media_file(source_media_file)
        if not source_thumbnail.exists():
            return renamed

        source_kind = self._media_kind_for(source_media_file)
        if source_kind == "audio":
            target_thumbnail = self.thumbnail_sidecar_path_for_media_file(target_media_file)
        else:
            target_thumbnail = self.thumbnail_path_for_media_file(target_media_file)

        if source_thumbnail == target_thumbnail:
            return True

        target_thumbnail.parent.mkdir(parents=True, exist_ok=True)
        if target_thumbnail.exists():
            source_thumbnail.unlink()
            return True

        shutil.move(str(source_thumbnail), str(target_thumbnail))
        return True

    def rename_thumbnail_sidecars_for_media_file(
        self,
        source_media_file: Path,
        target_media_file: Path,
    ) -> bool:
        """Rename adjacent thumbnail sidecars to match a moved media file."""
        renamed = False
        for source_thumbnail in self.adjacent_thumbnail_paths_for_media_file(source_media_file):
            if not source_thumbnail.exists():
                continue

            target_thumbnail = self.thumbnail_sidecar_path_for_media_file(
                target_media_file,
                source_thumbnail.suffix,
            )
            if source_thumbnail == target_thumbnail:
                renamed = True
                continue

            target_thumbnail.parent.mkdir(parents=True, exist_ok=True)
            if target_thumbnail.exists():
                source_thumbnail.unlink()
                renamed = True
                continue

            shutil.move(str(source_thumbnail), str(target_thumbnail))
            renamed = True
        return renamed

    @staticmethod
    def _media_kind_for(media_file: Path) -> str | None:
        suffix = media_file.suffix.lower()
        if suffix in _VIDEO_EXTENSIONS:
            return "video"
        if suffix in _AUDIO_EXTENSIONS:
            return "audio"
        return None
