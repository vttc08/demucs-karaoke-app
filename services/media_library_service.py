"""Media library query helpers for the media management page."""
from pathlib import Path
from typing import Any

from sqlalchemy import case, func
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
        tasks_by_media_id = self._latest_tasks_by_media_id(db, rows)
        return [
            self._to_page_item(row, tasks_by_media_id.get(row.id))
            for row in rows
        ]

    def get_media_stats(self, db: Session) -> dict[str, int]:
        total, with_multi_track, with_lyrics, missing = db.query(
            func.count(MediaItem.id),
            func.sum(
                case(
                    (
                        MediaItem.vocals_path.isnot(None)
                        & (MediaItem.vocals_path != ""),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        MediaItem.lyrics_path.isnot(None)
                        & (MediaItem.lyrics_path != ""),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((MediaItem.missing.is_(True), 1), else_=0)),
        ).one()
        return {
            "total": int(total or 0),
            "with_multi_track": int(with_multi_track or 0),
            "with_lyrics": int(with_lyrics or 0),
            "missing": int(missing or 0),
        }

    @staticmethod
    def _latest_tasks_by_media_id(
        db: Session,
        items: list[MediaItem],
    ) -> dict[int, ProcessingTask]:
        media_item_ids = [item.id for item in items]
        if not media_item_ids:
            return {}

        latest_task_ids = (
            db.query(func.max(ProcessingTask.id).label("task_id"))
            .filter(
                ProcessingTask.target_media_item_id.in_(media_item_ids),
                ProcessingTask.task_type == "media_karaoke",
                ProcessingTask.status.in_(
                    ["pending", "downloading", "processing", "failed"]
                ),
            )
            .group_by(ProcessingTask.target_media_item_id)
            .subquery()
        )
        tasks = (
            db.query(ProcessingTask)
            .join(latest_task_ids, ProcessingTask.id == latest_task_ids.c.task_id)
            .all()
        )
        return {
            task.target_media_item_id: task
            for task in tasks
            if task.target_media_item_id is not None
        }

    @staticmethod
    def _to_page_item(
        item: MediaItem,
        task: ProcessingTask | None,
    ) -> dict[str, Any]:
        lyrics_kind = None
        if item.lyrics_path and item.lyrics_path.strip():
            lyrics_kind = Path(item.lyrics_path).suffix.lower().lstrip(".") or None
        task_snapshot = task_stream_manager.snapshot_now(task.id) if task else None
        return {
            "id": item.id,
            "title": item.title,
            "artist": item.artist,
            "media_path": item.media_path,
            "lyrics_path": item.lyrics_path,
            "status": "missing" if item.missing else "synced",
            "thumbnail": MediaLibraryService._thumbnail_for(item),
            "has_multi_track": bool(item.vocals_path and item.vocals_path.strip()),
            "has_lyrics": bool(item.lyrics_path and item.lyrics_path.strip()),
            "lyrics_kind": lyrics_kind,
            "task_id": task.id if task else None,
            "task_status": task.status if task else None,
            "task_stage": task.stage if task else None,
            "task_progress": task_snapshot.get("progress_percent") if task_snapshot else None,
            "task_label": task_snapshot.get("progress_label") if task_snapshot else None,
            "task_label_key": task_snapshot.get("progress_label_key") if task_snapshot else None,
            "task_label_args": task_snapshot.get("progress_label_args") if task_snapshot else None,
            "task_mode": task_snapshot.get("progress_mode") if task_snapshot else None,
            "task_step_index": task_snapshot.get("progress_step_index") if task_snapshot else None,
            "task_step_total": task_snapshot.get("progress_step_total") if task_snapshot else None,
        }

    @staticmethod
    def _thumbnail_for(item: MediaItem) -> str | None:
        adjacent_thumbnail = MediaLibraryService._local_adjacent_thumbnail_for(item)
        if adjacent_thumbnail is not None:
            return adjacent_thumbnail

        youtube_thumbnail = MediaLibraryService._youtube_thumbnail_for(item)
        if youtube_thumbnail is not None:
            return youtube_thumbnail

        media_file = QueueService._media_url_to_file(item.media_path)
        if media_file is None:
            return None

        thumbnail_path = MediaThumbnailService.best_thumbnail_path_for_media_file(media_file)
        if thumbnail_path is None:
            return None
        return MediaThumbnailService.thumbnail_url_for_media_file(media_file)

    @staticmethod
    def _local_adjacent_thumbnail_for(item: MediaItem) -> str | None:
        media_file = QueueService._media_url_to_file(item.media_path)
        if media_file is None:
            return None
        for candidate in MediaThumbnailService.adjacent_thumbnail_paths_for_media_file(media_file):
            if candidate.exists():
                return MediaThumbnailService.public_url_for_path(candidate)
        return None

    @staticmethod
    def _youtube_thumbnail_for(item: MediaItem) -> str | None:
        if item.youtube_id:
            youtube_id = item.youtube_id.strip()
            if youtube_id:
                return f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg"

        return None
