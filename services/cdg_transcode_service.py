"""CDG-to-MP4 conversion helpers for legacy MP3+G library items."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from adapters.ffmpeg import FFmpegAdapter
from config import settings
from models import MediaItem, utc_now
from services.media_thumbnail_service import MediaThumbnailService
from services.queue_service import QueueService

logger = logging.getLogger(__name__)


class CdgTranscodeError(ValueError):
    """Raised when a CDG transcode request is invalid or cannot be completed."""


class CdgTranscodeService:
    """Render CDG graphics into a playable MP4 and update the media library."""

    def __init__(self, ffmpeg: FFmpegAdapter | None = None):
        self.ffmpeg = ffmpeg or FFmpegAdapter()
        self.queue_service = QueueService()
        self.thumbnail_service = MediaThumbnailService()

    def transcode_media_item(
        self,
        db: Session,
        media_item_id: int,
        *,
        task_id: int,
        overwrite_original: bool = False,
        cancel_event=None,
    ) -> dict[str, Any]:
        """Transcode one CDG-backed item into an MP4 file."""
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise CdgTranscodeError(f"Media item not found: {media_item_id}")

        media_file = self.queue_service._media_url_to_file(media_item.media_path)
        lyrics_file = self.queue_service._media_url_to_file(media_item.lyrics_path)
        if media_file is None or not media_file.is_file():
            raise CdgTranscodeError("Media file is missing")
        if lyrics_file is None or not lyrics_file.is_file():
            raise CdgTranscodeError("CDG lyrics file is missing")
        if lyrics_file.suffix.lower() != ".cdg":
            raise CdgTranscodeError("Media item does not use a CDG lyrics sidecar")

        base_stem = media_item.file_stem or media_file.stem or f"media-{media_item.id}"
        if overwrite_original:
            output_stem = self._allocate_output_stem(db, base_stem, exclude_media_id=media_item.id)
        else:
            output_stem = self._allocate_output_stem(db, f"{base_stem} - CDG")

        output_path = settings.media_path / f"{output_stem}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        scratch_dir = settings.cache_path / "processed" / str(task_id)
        scratch_dir.mkdir(parents=True, exist_ok=True)
        staged_output = scratch_dir / output_path.name

        self.ffmpeg.transcode_cdg_to_mp4(
            lyrics_file,
            media_file,
            staged_output,
            audio_codec=settings.ffmpeg_audio_codec,
            cancel_event=cancel_event,
        )

        if not staged_output.exists() or staged_output.stat().st_size == 0:
            raise CdgTranscodeError("Transcode produced an empty output")

        probe = self.ffmpeg.probe_media(staged_output)
        if not probe["has_video"] or not probe["has_audio"]:
            raise CdgTranscodeError("Transcode output is missing video or audio")

        if output_path.exists():
            output_path.unlink()
        os.replace(staged_output, output_path)

        if overwrite_original:
            original_media_path = media_file
            original_lyrics_path = lyrics_file
            media_item.media_path = self.queue_service.build_media_url(output_path)
            media_item.lyrics_path = None
            media_item.file_stem = output_stem
            media_item.missing = False
            media_item.updated_at = utc_now()
            db.commit()
            self._cleanup_original_paths(original_media_path, original_lyrics_path)
            self.thumbnail_service.remove_thumbnail_for_media_file(original_media_path)
            self.thumbnail_service.remove_thumbnail_sidecars_for_media_file(original_media_path)
            self.thumbnail_service.ensure_thumbnail_for_media_file(output_path)
            logger.info(
                "CDG transcode overwrote media item media_id=%s output=%s",
                media_item_id,
                output_path,
            )
            return {
                "media_item_id": media_item_id,
                "output_media_item_id": media_item.id,
                "output_media_path": media_item.media_path,
                "overwrite_original": True,
                "output_stem": output_stem,
                "source_media_path": self.queue_service.build_media_url(original_media_path),
                "source_lyrics_path": self.queue_service.build_media_url(original_lyrics_path),
                "task_id": task_id,
            }

        new_media_item = MediaItem(
            youtube_id=None,
            file_stem=output_stem,
            title=media_item.title,
            artist=media_item.artist,
            media_path=self.queue_service.build_media_url(output_path),
            lyrics_path=None,
            vocals_path=None,
            missing=False,
            last_scanned_at=utc_now(),
        )
        db.add(new_media_item)
        db.commit()
        db.refresh(new_media_item)
        self.thumbnail_service.ensure_thumbnail_for_media_file(output_path)
        logger.info(
            "CDG transcode created media item source_media_id=%s output_media_id=%s output=%s",
            media_item_id,
            new_media_item.id,
            output_path,
        )
        return {
            "media_item_id": media_item_id,
            "output_media_item_id": new_media_item.id,
            "output_media_path": new_media_item.media_path,
            "overwrite_original": False,
            "output_stem": output_stem,
            "task_id": task_id,
        }

    def _allocate_output_stem(
        self,
        db: Session,
        base_stem: str,
        *,
        exclude_media_id: int | None = None,
    ) -> str:
        candidate = base_stem
        suffix = 2
        while self._stem_in_use(db, candidate, exclude_media_id=exclude_media_id):
            candidate = f"{base_stem} ({suffix})"
            suffix += 1
        return candidate

    def _stem_in_use(
        self,
        db: Session,
        stem: str,
        *,
        exclude_media_id: int | None = None,
    ) -> bool:
        query = db.query(MediaItem)
        if exclude_media_id is not None:
            query = query.filter(MediaItem.id != exclude_media_id)
        stem_lower = stem.lower()
        for item in query.all():
            for media_url in (item.media_path, item.lyrics_path, item.vocals_path):
                media_file = self.queue_service._media_url_to_file(media_url)
                if media_file is None:
                    continue
                if media_file.stem.lower().startswith(stem_lower):
                    return True
        return False

    def _cleanup_original_paths(self, *paths: Path) -> None:
        for path in paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                logger.exception("Failed to remove original CDG source path path=%s", path)
