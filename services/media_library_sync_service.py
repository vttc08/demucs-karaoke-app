"""Filesystem reconciliation for persisted media library rows."""
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from config import settings
from models import MediaItem
from services.queue_service import QueueService
from services.media_thumbnail_service import MediaThumbnailService

logger = logging.getLogger(__name__)

_PRIMARY_MEDIA_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".avi",
    ".m4v",
    ".mp3",
    ".wav",
    ".m4a",
    ".flac",
    ".aac",
    ".ogg",
    ".opus",
}
_VOCALS_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm")
_LYRICS_EXTENSIONS = (".json", ".lrc", ".srt", ".txt")


class MediaLibrarySyncService:
    """Sync media_items rows with files under the configured media root."""

    def __init__(self):
        self.queue_service = QueueService()
        self.thumbnail_service = MediaThumbnailService()

    def scan_library(self, db: Session) -> dict[str, int]:
        """Reconcile database media rows with current filesystem state."""
        scanned_at = datetime.utcnow()
        media_files = self._discover_primary_media_files(settings.media_path)
        files_by_url = {
            self.queue_service.build_media_url(path): path
            for path in media_files
        }

        rows = db.query(MediaItem).all()
        rows_by_url: dict[str, MediaItem] = {}
        skipped_rows = 0
        for row in rows:
            normalized_url = self._normalize_media_url(row.media_path)
            if not normalized_url:
                skipped_rows += 1
                continue
            rows_by_url[normalized_url] = row

        marked_missing = 0
        restored = 0
        sidecars_updated = 0
        thumbnails_updated = 0

        for media_url, row in rows_by_url.items():
            media_file = files_by_url.get(media_url)
            if media_file is None:
                if not row.missing:
                    marked_missing += 1
                row.missing = True
                row.last_scanned_at = scanned_at
                continue

            restored_delta, sidecars_delta, thumbnails_delta = self._scan_existing_media_row(
                row,
                media_file,
                scanned_at,
            )
            restored += restored_delta
            sidecars_updated += sidecars_delta
            thumbnails_updated += thumbnails_delta

        created = 0
        for media_url, media_file in files_by_url.items():
            if media_url in rows_by_url:
                continue
            new_item = MediaItem(
                title=media_file.stem,
                artist=None,
                file_stem=media_file.stem,
                media_path=media_url,
                missing=False,
                last_scanned_at=scanned_at,
            )
            if self._refresh_sidecars(new_item, media_file):
                sidecars_updated += 1
            if self.thumbnail_service.ensure_thumbnail_for_media_file(media_file):
                thumbnails_updated += 1
            db.add(new_item)
            created += 1

        db.commit()

        summary = {
            "scanned_files": len(media_files),
            "created": created,
            "marked_missing": marked_missing,
            "restored": restored,
            "sidecars_updated": sidecars_updated,
            "thumbnails_updated": thumbnails_updated,
            "skipped_rows": skipped_rows,
        }
        logger.info(
            "Media library scan complete scanned_files=%s created=%s marked_missing=%s restored=%s sidecars_updated=%s thumbnails_updated=%s skipped_rows=%s",
            summary["scanned_files"],
            summary["created"],
            summary["marked_missing"],
            summary["restored"],
            summary["sidecars_updated"],
            summary["thumbnails_updated"],
            summary["skipped_rows"],
        )
        return summary

    def scan_media_item(self, db: Session, media_item_id: int) -> dict[str, int]:
        """Refresh sidecar and missing-state information for one media item."""
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise ValueError(f"Media item not found: {media_item_id}")

        scanned_at = datetime.utcnow()
        media_file = self.queue_service._media_url_to_file(media_item.media_path)
        if media_file is None:
            logger.info(
                "Skipping media item scan because the media path is not scanable media_id=%s media_path=%s",
                media_item_id,
                media_item.media_path,
            )
            return {
                "scanned_files": 0,
                "created": 0,
                "marked_missing": 0,
                "restored": 0,
                "sidecars_updated": 0,
                "thumbnails_updated": 0,
                "skipped_rows": 1,
            }

        if media_file.exists():
            restored, sidecars_updated, thumbnails_updated = self._scan_existing_media_row(
                media_item,
                media_file,
                scanned_at,
            )
            marked_missing = 0
        else:
            restored = 0
            sidecars_updated = 0
            thumbnails_updated = 0
            marked_missing = 0 if media_item.missing else 1
            media_item.missing = True
            media_item.last_scanned_at = scanned_at

        db.commit()

        summary = {
            "scanned_files": 1,
            "created": 0,
            "marked_missing": marked_missing,
            "restored": restored,
            "sidecars_updated": sidecars_updated,
            "thumbnails_updated": thumbnails_updated,
            "skipped_rows": 0,
        }
        logger.info(
            "Media item scan complete media_id=%s scanned_files=%s marked_missing=%s restored=%s sidecars_updated=%s thumbnails_updated=%s skipped_rows=%s",
            media_item_id,
            summary["scanned_files"],
            summary["marked_missing"],
            summary["restored"],
            summary["sidecars_updated"],
            summary["thumbnails_updated"],
            summary["skipped_rows"],
        )
        return summary

    def _discover_primary_media_files(self, media_root: Path) -> list[Path]:
        if not media_root.exists():
            return []
        results: list[Path] = []
        for candidate in media_root.rglob("*"):
            if not candidate.is_file():
                continue
            suffix = candidate.suffix.lower()
            if suffix not in _PRIMARY_MEDIA_EXTENSIONS:
                continue
            if candidate.stem.lower().endswith(".vocals"):
                continue
            if candidate.stem.lower().endswith(".audio"):
                continue
            if self._is_legacy_karaoke_duplicate(candidate):
                continue
            results.append(candidate.resolve())
        results.sort()
        return results

    @staticmethod
    def _is_legacy_karaoke_duplicate(candidate: Path) -> bool:
        stem = candidate.stem
        if not stem.lower().endswith(".karaoke"):
            return False
        canonical_stem = stem[: -len(".karaoke")]
        canonical_candidate = candidate.with_name(f"{canonical_stem}{candidate.suffix}")
        return canonical_candidate.exists() and canonical_candidate.is_file()

    def _refresh_sidecars(self, media_item: MediaItem, media_file: Path) -> bool:
        expected_vocals = self._find_vocals_sidecar(media_file)
        expected_lyrics = self._find_lyrics_sidecar(media_file)
        current_vocals = self._normalize_optional_url(media_item.vocals_path)
        current_lyrics = self._normalize_optional_url(media_item.lyrics_path)
        changed = current_vocals != expected_vocals or current_lyrics != expected_lyrics
        media_item.vocals_path = expected_vocals
        media_item.lyrics_path = expected_lyrics
        return changed

    def _scan_existing_media_row(
        self,
        media_item: MediaItem,
        media_file: Path,
        scanned_at: datetime,
    ) -> tuple[int, int, int]:
        """Refresh one existing media row from its backing file."""
        restored = int(media_item.missing)
        media_item.missing = False
        media_item.last_scanned_at = scanned_at
        media_item.file_stem = media_item.file_stem or media_file.stem

        sidecars_updated = 1 if self._refresh_sidecars(media_item, media_file) else 0
        thumbnails_updated = 0
        if self._should_refresh_thumbnail(media_item, media_file):
            thumbnails_updated = 1 if self.thumbnail_service.ensure_thumbnail_for_media_file(media_file) else 0
        return restored, sidecars_updated, thumbnails_updated

    def _find_vocals_sidecar(self, media_file: Path) -> str | None:
        for stem in self._sidecar_stems_for_media(media_file):
            for ext in _VOCALS_AUDIO_EXTENSIONS:
                candidate = media_file.with_name(f"{stem}.vocals{ext}")
                if candidate.exists() and candidate.is_file():
                    return self.queue_service.build_media_url(candidate)
        return None

    def _find_lyrics_sidecar(self, media_file: Path) -> str | None:
        for stem in self._sidecar_stems_for_media(media_file):
            for ext in _LYRICS_EXTENSIONS:
                candidate = media_file.with_name(f"{stem}{ext}")
                if candidate.exists() and candidate.is_file():
                    return self.queue_service.build_media_url(candidate)
        return None

    @staticmethod
    def _sidecar_stems_for_media(media_file: Path) -> list[str]:
        stems = [media_file.stem]
        if media_file.stem.lower().endswith(".karaoke"):
            stems.append(media_file.stem[: -len(".karaoke")])
        return stems

    def _normalize_media_url(self, value: str | None) -> str | None:
        if value is None:
            return None
        raw = value.strip()
        if not raw:
            return None
        if raw.startswith("/media/"):
            return raw
        try:
            return self.queue_service.build_media_url(Path(raw))
        except ValueError:
            return None

    @staticmethod
    def _normalize_optional_url(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def _should_refresh_thumbnail(self, media_item: MediaItem, media_file: Path) -> bool:
        """Return whether scan refresh should touch the thumbnail cache for this row."""
        if not media_item.youtube_id:
            return True
        return any(
            candidate.exists()
            for candidate in self.thumbnail_service.adjacent_thumbnail_paths_for_media_file(media_file)
        )
