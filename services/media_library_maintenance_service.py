"""Media library maintenance helpers for destructive actions."""
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from models import MediaItem, QueueItem, QueueStatus
from services.queue_service import QueueService

logger = logging.getLogger(__name__)

_VOCALS_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm")
_LYRICS_EXTENSIONS = (".lrc", ".srt", ".txt")


class MediaItemNotFoundError(ValueError):
    """Raised when the requested media item does not exist."""


class MediaItemDeleteConflictError(ValueError):
    """Raised when a media item cannot be deleted safely."""


class MediaLibraryMaintenanceService:
    """Service for media item cleanup and deletion."""

    def __init__(self):
        self.queue_service = QueueService()

    def delete_media_item(self, db: Session, media_item_id: int) -> dict[str, int]:
        """Delete a media item, associated queue rows, and local files."""
        media_item = (
            db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        )
        if media_item is None:
            raise MediaItemNotFoundError(f"Media item not found: {media_item_id}")

        playing_queue_item = (
            db.query(QueueItem)
            .filter(
                QueueItem.media_id == media_item_id,
                QueueItem.status == QueueStatus.PLAYING.value,
            )
            .first()
        )
        if playing_queue_item is not None:
            raise MediaItemDeleteConflictError(
                "Cannot delete a media item that is currently playing"
            )

        local_paths = self._collect_local_paths(media_item)
        deleted_files = 0
        missing_files = 0
        for path in local_paths:
            if not path.exists():
                missing_files += 1
                continue
            logger.info("Deleting media file path=%s media_id=%s", path, media_item_id)
            path.unlink()
            deleted_files += 1

        removed_queue_items = (
            db.query(QueueItem)
            .filter(QueueItem.media_id == media_item_id)
            .delete(synchronize_session=False)
        )
        db.delete(media_item)
        db.commit()

        summary = {
            "deleted_files": deleted_files,
            "missing_files": missing_files,
            "removed_queue_items": int(removed_queue_items or 0),
        }
        logger.info(
            "Media item deleted media_id=%s deleted_files=%s missing_files=%s removed_queue_items=%s",
            media_item_id,
            summary["deleted_files"],
            summary["missing_files"],
            summary["removed_queue_items"],
        )
        return summary

    def _collect_local_paths(self, media_item: MediaItem) -> list[Path]:
        """Collect unique local filesystem paths for the media item and sidecars."""
        candidates: list[Path] = []
        seen: set[str] = set()

        def add_candidate(path: Path | None) -> None:
            if path is None:
                return
            key = str(path)
            if key in seen:
                return
            seen.add(key)
            candidates.append(path)

        media_file = self.queue_service._media_url_to_file(media_item.media_path)
        add_candidate(media_file)
        add_candidate(self.queue_service._media_url_to_file(media_item.vocals_path))
        add_candidate(self.queue_service._media_url_to_file(media_item.lyrics_path))

        if media_file is None:
            return candidates

        stem = media_file.stem
        for ext in _VOCALS_AUDIO_EXTENSIONS:
            candidate = media_file.with_name(f"{stem}.vocals{ext}")
            if candidate.exists():
                add_candidate(candidate)
        for ext in _LYRICS_EXTENSIONS:
            candidate = media_file.with_suffix(ext)
            if candidate.exists():
                add_candidate(candidate)

        return candidates
