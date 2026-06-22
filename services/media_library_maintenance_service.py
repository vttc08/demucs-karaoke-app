"""Media library maintenance helpers for destructive actions."""
import logging
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

from sqlalchemy.orm import Session

from config import settings
from models import MediaItem, QueueItem, QueueStatus
from services.media_naming import build_media_stem
from services.media_thumbnail_service import MediaThumbnailService
from services.queue_service import QueueService

logger = logging.getLogger(__name__)

_VOCALS_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm")
_LYRICS_EXTENSIONS = (".json", ".lrc", ".srt", ".txt")
_FILE_KIND_ORDER = ("main", "vocals", "lyrics")


class MediaItemNotFoundError(ValueError):
    """Raised when the requested media item does not exist."""


class MediaItemDeleteConflictError(ValueError):
    """Raised when a media item cannot be deleted safely."""


class MediaItemRenameConflictError(ValueError):
    """Raised when a media item rename would overwrite another file."""


class MediaFileKindError(ValueError):
    """Raised when a media file kind is unsupported."""


class MediaFileDeleteConflictError(ValueError):
    """Raised when a media file cannot be deleted safely."""


class MediaFileNotFoundError(ValueError):
    """Raised when a requested media file is not available."""


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

    def get_media_file_manifest(self, db: Session, media_item_id: int) -> dict[str, object]:
        """Return media, vocals, and lyrics file metadata for the edit modal."""
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise MediaItemNotFoundError(f"Media item not found: {media_item_id}")

        entries = self._collect_media_file_entries(media_item)
        has_multi_track = any(entry["kind"] == "vocals" and entry["exists"] for entry in entries)
        has_lyrics = any(entry["kind"] == "lyrics" and entry["exists"] for entry in entries)
        lyrics_kind = next(
            (entry["extension"] for entry in entries if entry["kind"] == "lyrics" and entry["exists"]),
            None,
        )

        return {
            "media_id": media_item.id,
            "title": media_item.title,
            "artist": media_item.artist,
            "download_name": f"{self._media_package_stem(media_item)}.zip",
            "has_multi_track": has_multi_track,
            "has_lyrics": has_lyrics,
            "lyrics_kind": lyrics_kind,
            "files": [
                {key: value for key, value in entry.items() if key != "file_path"}
                for entry in entries
            ],
        }

    def get_media_file(self, db: Session, media_item_id: int, kind: str) -> tuple[MediaItem, Path, dict[str, object]]:
        """Resolve one media file entry for download or deletion."""
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise MediaItemNotFoundError(f"Media item not found: {media_item_id}")

        entry = self._resolve_media_file_entry(media_item, kind, include_missing=True)
        if entry is None:
            raise MediaFileKindError(f"Unsupported media file kind: {kind}")

        file_path = entry.get("file_path")
        if not isinstance(file_path, Path):
            raise MediaFileNotFoundError(f"Media file not found: {kind}")
        return media_item, file_path, entry

    def delete_media_file(self, db: Session, media_item_id: int, kind: str) -> dict[str, object]:
        """Delete a tracked sidecar file and clear the matching DB field."""
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise MediaItemNotFoundError(f"Media item not found: {media_item_id}")

        if kind == "main":
            raise MediaFileDeleteConflictError("The main media file cannot be deleted from the modal")

        entry = self._resolve_media_file_entry(media_item, kind, include_missing=True)
        if entry is None:
            raise MediaFileKindError(f"Unsupported media file kind: {kind}")

        file_path = entry.get("file_path")
        if not isinstance(file_path, Path):
            raise MediaFileNotFoundError(f"Media file not found: {kind}")

        existed = file_path.exists()
        if existed:
            logger.info("Deleting media sidecar path=%s media_id=%s kind=%s", file_path, media_item_id, kind)
            file_path.unlink()

        if kind == "vocals":
            current_value = self.queue_service._media_url_to_file(media_item.vocals_path)
            if current_value is None or current_value.resolve() == file_path.resolve():
                media_item.vocals_path = None
        elif kind == "lyrics":
            current_value = self.queue_service._media_url_to_file(media_item.lyrics_path)
            if current_value is None or current_value.resolve() == file_path.resolve():
                media_item.lyrics_path = None
        else:
            raise MediaFileKindError(f"Unsupported media file kind: {kind}")

        db.commit()
        return {
            "deleted": existed,
            "kind": kind,
            "filename": file_path.name,
            "path": self.queue_service.build_media_url(file_path),
            "exists": file_path.exists(),
        }

    def build_media_zip(self, db: Session, media_item_id: int) -> tuple[bytes, str]:
        """Build a ZIP package containing the media file and tracked sidecars."""
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise MediaItemNotFoundError(f"Media item not found: {media_item_id}")

        main_entry = self._resolve_media_file_entry(media_item, "main", include_missing=True)
        if main_entry is None:
            raise MediaFileKindError("Unsupported media file kind: main")
        main_path = main_entry.get("file_path")
        if not isinstance(main_path, Path) or not main_path.exists():
            raise MediaFileNotFoundError("Main media file is missing")

        archive_name = f"{self._media_package_stem(media_item)}.zip"
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
            for entry in self._collect_media_file_entries(media_item):
                file_path = entry.get("file_path")
                if not isinstance(file_path, Path) or not file_path.exists():
                    continue
                archive.write(file_path, arcname=file_path.name)
            thumbnail_entry = self._thumbnail_zip_entry(media_item)
            if thumbnail_entry is not None:
                thumbnail_path, thumbnail_name = thumbnail_entry
                if thumbnail_path.exists():
                    archive.write(thumbnail_path, arcname=thumbnail_name)
        return buffer.getvalue(), archive_name

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
            for candidate in self.thumbnail_service.adjacent_thumbnail_paths_for_media_file(media_file):
                if candidate.exists():
                    add_candidate(candidate)

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

    def _collect_media_file_entries(
        self,
        media_item: MediaItem,
        *,
        include_missing: bool = False,
    ) -> list[dict[str, object]]:
        """Collect main and sidecar file entries for UI and download workflows."""
        media_file = self.queue_service._media_url_to_file(media_item.media_path)
        vocals_url, lyrics_url = self.queue_service._repair_sidecar_fields(
            media_path=media_item.media_path,
            vocals_path=media_item.vocals_path,
            lyrics_path=media_item.lyrics_path,
        )

        resolved_files: dict[str, Path | None] = {
            "main": media_file,
            "vocals": self.queue_service._media_url_to_file(vocals_url),
            "lyrics": self.queue_service._media_url_to_file(lyrics_url),
        }
        stored_urls = {
            "main": media_item.media_path,
            "vocals": vocals_url,
            "lyrics": lyrics_url,
        }

        entries: list[dict[str, object]] = []
        for kind in _FILE_KIND_ORDER:
            file_path = resolved_files[kind]
            stored_url = stored_urls[kind]
            exists = bool(file_path and file_path.exists())
            if not exists and not include_missing:
                continue
            filename = file_path.name if file_path is not None else self._fallback_filename(media_item, kind)
            extension = file_path.suffix.lower().lstrip(".") if file_path is not None else ""
            entries.append(
                {
                    "kind": kind,
                    "label": self._file_kind_label(kind, file_path),
                    "filename": filename,
                    "path": stored_url,
                    "exists": exists,
                    "downloadable": exists,
                    "deletable": kind != "main",
                    "extension": extension,
                    "file_path": file_path,
                }
            )
        return entries

    @staticmethod
    def _fallback_filename(media_item: MediaItem, kind: str) -> str:
        stem = Path(media_item.media_path).stem if media_item.media_path else media_item.file_stem or media_item.title
        if kind == "main":
            return Path(media_item.media_path).name if media_item.media_path else f"{stem}.mp4"
        if kind == "vocals":
            return f"{stem}.vocals"
        return f"{stem}.lyrics"

    @staticmethod
    def _file_kind_label(kind: str, file_path: Path | None) -> str:
        if kind == "main":
            return "main"
        if kind == "vocals":
            return "vocals"
        if kind != "lyrics":
            return kind
        if file_path is None:
            return "lyrics"
        suffix = file_path.suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix == ".lrc":
            return "lrc"
        if suffix == ".txt":
            return "txt"
        if suffix == ".srt":
            return "srt"
        return "lyrics"

    @staticmethod
    def _media_package_stem(media_item: MediaItem) -> str:
        media_file = Path(media_item.media_path).name if media_item.media_path else ""
        if media_file:
            return Path(media_file).stem
        if media_item.file_stem:
            return media_item.file_stem
        return build_media_stem(media_item.title, media_item.artist)

    def _thumbnail_zip_entry(self, media_item: MediaItem) -> tuple[Path, str] | None:
        """Return the thumbnail file and ZIP entry name, if any thumbnail exists."""
        media_file = self.queue_service._media_url_to_file(media_item.media_path)
        if media_file is None:
            return None

        thumbnail_path = MediaThumbnailService.best_thumbnail_path_for_media_file(media_file)
        if thumbnail_path is None:
            return None

        if thumbnail_path.parent == media_file.parent:
            return thumbnail_path, thumbnail_path.name

        return thumbnail_path, f"{self._media_package_stem(media_item)}{thumbnail_path.suffix.lower()}"

    def _resolve_media_file_entry(
        self,
        media_item: MediaItem,
        kind: str,
        *,
        include_missing: bool = False,
    ) -> dict[str, object] | None:
        entries = self._collect_media_file_entries(media_item, include_missing=include_missing)
        for entry in entries:
            if entry["kind"] == kind:
                return entry
        return None

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
