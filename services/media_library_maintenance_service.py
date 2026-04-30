"""Media library maintenance helpers for destructive actions."""
import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from config import settings
from models import MediaItem, QueueItem, QueueStatus
from services.media_naming import build_media_stem
from services.media_thumbnail_service import MediaThumbnailService
from services.queue_service import QueueService

logger = logging.getLogger(__name__)

_VOCALS_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm")
_LYRICS_EXTENSIONS = (".lrc", ".srt", ".txt")


class MediaItemNotFoundError(ValueError):
    """Raised when the requested media item does not exist."""


class MediaItemDeleteConflictError(ValueError):
    """Raised when a media item cannot be deleted safely."""


class MediaItemRenameConflictError(ValueError):
    """Raised when a media item rename would overwrite another file."""


class MediaLibraryMaintenanceService:
    """Service for media item cleanup and deletion."""

    def __init__(self):
        self.queue_service = QueueService()
        self.thumbnail_service = MediaThumbnailService()

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

    def rename_media_item(
        self,
        db: Session,
        media_item_id: int,
        title: str,
        artist: str | None,
        rename_on_disk: bool,
    ) -> dict[str, int | str | None]:
        """Rename a media item in the database, and optionally on disk."""
        media_item = (
            db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        )
        if media_item is None:
            raise MediaItemNotFoundError(f"Media item not found: {media_item_id}")

        normalized_title = self.queue_service._normalize_required_metadata(title)
        normalized_artist = self.queue_service._normalize_optional_metadata(artist)
        media_item.title = normalized_title
        media_item.artist = normalized_artist

        renamed_files = 0
        target_stem: str | None = None
        if rename_on_disk:
            source_media_path = self.queue_service._media_url_to_file(media_item.media_path)
            target_stem = self.queue_service._allocate_media_stem(
                db,
                build_media_stem(
                    normalized_title,
                    normalized_artist,
                    fallback=media_item.youtube_id,
                ),
                media_item.youtube_id,
                media_item.id,
            )
            current_media_path = self.queue_service._media_url_to_file(media_item.media_path)
            current_vocals_path, current_lyrics_path = self.queue_service._repair_sidecar_fields(
                media_path=media_item.media_path,
                vocals_path=media_item.vocals_path,
                lyrics_path=media_item.lyrics_path,
            )

            new_media_path, media_renamed = self._rename_local_asset(
                current_media_path,
                target_stem,
                "media",
                settings.media_path,
            )
            new_vocals_path, vocals_renamed = self._rename_local_asset(
                self.queue_service._media_url_to_file(current_vocals_path),
                target_stem,
                "vocals",
                settings.media_path,
            )
            new_lyrics_path, lyrics_renamed = self._rename_local_asset(
                self.queue_service._media_url_to_file(current_lyrics_path),
                target_stem,
                "lyrics",
                None,
            )

            renamed_files = int(media_renamed) + int(vocals_renamed) + int(lyrics_renamed)
            if media_renamed:
                media_item.media_path = self.queue_service.build_media_url(new_media_path)
                media_item.missing = False
                media_item.file_stem = target_stem
                if source_media_path is not None:
                    self.thumbnail_service.rename_thumbnail_for_media_file(
                        source_media_path,
                        new_media_path,
                    )
            if vocals_renamed:
                media_item.vocals_path = self.queue_service.build_media_url(new_vocals_path)
                media_item.file_stem = target_stem
            if lyrics_renamed:
                media_item.lyrics_path = self.queue_service.build_media_url(new_lyrics_path)
                media_item.file_stem = target_stem

        db.commit()

        summary: dict[str, int | str | None] = {
            "renamed_files": renamed_files,
            "target_stem": target_stem,
        }
        logger.info(
            "Media item renamed media_id=%s rename_on_disk=%s renamed_files=%s target_stem=%s",
            media_item_id,
            rename_on_disk,
            renamed_files,
            target_stem,
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
        if media_file is not None:
            add_candidate(MediaThumbnailService.thumbnail_path_for_media_file(media_file))

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

    def _rename_local_asset(
        self,
        source_path: Path | None,
        target_stem: str,
        media_kind: str,
        target_root: Path | None,
    ) -> tuple[Path | None, bool]:
        """Rename a media asset if it exists and return the new path."""
        if source_path is None or not source_path.exists():
            return source_path, False

        if media_kind == "vocals":
            target_name = f"{target_stem}.vocals{source_path.suffix}"
        else:
            target_name = f"{target_stem}{source_path.suffix}"
        target_path = (
            (target_root or source_path.parent) / target_name
            if target_root is not None
            else source_path.with_name(target_name)
        )
        if source_path == target_path:
            return source_path, False
        if target_path.exists():
            raise MediaItemRenameConflictError(
                f"Target path already exists: {target_path}"
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(target_path))
        return target_path, True
