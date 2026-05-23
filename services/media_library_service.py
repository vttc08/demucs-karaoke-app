"""Media library query helpers for the media management page."""
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import MediaItem, ProcessingTask
from services.media_thumbnail_service import MediaThumbnailService
from services.queue_service import QueueService
from services.task_stream_service import task_stream_manager


class MediaLibraryService:
    """Service for read-only media library page data."""

    def list_media_items(self, db: Session) -> list[dict[str, Any]]:
        rows = (
            db.query(MediaItem)
            .order_by(MediaItem.updated_at.desc(), MediaItem.id.desc())
            .all()
        )
        return [self._to_page_item(db, row) for row in rows]

    def get_media_stats(self, db: Session) -> dict[str, int]:
        total = int(db.query(func.count(MediaItem.id)).scalar() or 0)
        with_multi_track = int(
            db.query(func.count(MediaItem.id))
            .filter(MediaItem.vocals_path.isnot(None), MediaItem.vocals_path != "")
            .scalar()
            or 0
        )
        with_lyrics = int(
            db.query(func.count(MediaItem.id))
            .filter(MediaItem.lyrics_path.isnot(None), MediaItem.lyrics_path != "")
            .scalar()
            or 0
        )
        missing = int(
            db.query(func.count(MediaItem.id)).filter(MediaItem.missing.is_(True)).scalar()
            or 0
        )
        return {
            "total": total,
            "with_multi_track": with_multi_track,
            "with_lyrics": with_lyrics,
            "missing": missing,
        }

    @staticmethod
    def _to_page_item(db: Session, item: MediaItem) -> dict[str, Any]:
        task = (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.target_media_item_id == item.id,
                ProcessingTask.task_type == "media_karaoke",
                ProcessingTask.status.in_(["pending", "downloading", "processing", "failed"]),
            )
            .order_by(ProcessingTask.id.desc())
            .first()
        )
        task_snapshot = task_stream_manager.snapshot_now(task.id) if task else None
        return {
            "id": item.id,
            "title": item.title,
            "artist": item.artist,
            "media_path": item.media_path,
            "status": "missing" if item.missing else "synced",
            "thumbnail": MediaLibraryService._thumbnail_for(item),
            "has_multi_track": bool(item.vocals_path and item.vocals_path.strip()),
            "has_lyrics": bool(item.lyrics_path and item.lyrics_path.strip()),
            "task_id": task.id if task else None,
            "task_status": task.status if task else None,
            "task_stage": task.stage if task else None,
            "task_progress": task_snapshot.get("progress_percent") if task_snapshot else None,
            "task_label": task_snapshot.get("progress_label") if task_snapshot else None,
        }

    @staticmethod
    def _thumbnail_for(item: MediaItem) -> str | None:
        if item.youtube_id:
            youtube_id = item.youtube_id.strip()
            if youtube_id:
                return f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg"

        media_file = QueueService._media_url_to_file(item.media_path)
        if media_file is None:
            return None
        thumbnail_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        if not thumbnail_path.exists():
            return None
        return MediaThumbnailService.thumbnail_url_for_media_file(media_file)
