"""Durable processing-task operations and orchestration helpers."""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    MediaItem,
    ProcessingTask,
    ProcessingTaskResponse,
    ProcessingTaskSnapshotResponse,
    ProcessingTaskStatus,
    QueueItem,
    QueueStatus,
)
from services.media_library_maintenance_service import MediaLibraryMaintenanceService
from services.task_stream_service import task_stream_manager

logger = logging.getLogger(__name__)


def utc_now_naive() -> datetime:
    """Return naive UTC datetime for SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProcessingTaskService:
    """Manage durable tasks and their live stream state."""

    VOCAL_SYNC_PREPARE_TASK_TYPES = (
        "media_vocal_sync_prepare_youtube",
        "media_vocal_sync_prepare_upload",
    )
    ACTIVE_STATUSES = (
        ProcessingTaskStatus.PENDING.value,
        ProcessingTaskStatus.DOWNLOADING.value,
        ProcessingTaskStatus.PROCESSING.value,
    )
    CANCELLABLE_STATUSES = ACTIVE_STATUSES

    def get_or_create_queue_task(self, db: Session, queue_item_id: int) -> ProcessingTask:
        """Return an existing active queue task or create one."""
        active = (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.target_queue_item_id == queue_item_id,
                ProcessingTask.status.in_(self.ACTIVE_STATUSES),
            )
            .order_by(ProcessingTask.id.desc())
            .first()
        )
        if active is not None:
            return active

        queue_item = db.query(QueueItem).filter(QueueItem.id == queue_item_id).first()
        if queue_item is None:
            raise ValueError(f"Queue item not found: {queue_item_id}")
        source_kind = "youtube"
        if queue_item.media and not queue_item.media.youtube_id:
            source_kind = "library_media"
        task = ProcessingTask(
            task_type="queue_prepare",
            source_kind=source_kind,
            target_queue_item_id=queue_item_id,
            target_media_item_id=queue_item.media_id,
            status=ProcessingTaskStatus.PENDING.value,
            stage="queued",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def get_or_create_media_task(self, db: Session, media_item_id: int) -> ProcessingTask:
        """Return an existing active media karaoke task or create one."""
        return self._get_or_create_media_task(db, media_item_id, task_type="media_karaoke")

    def get_or_create_media_karaoke_align_task(self, db: Session, media_item_id: int) -> ProcessingTask:
        """Return an existing active media separation+alignment task or create one."""
        return self._get_or_create_media_task(db, media_item_id, task_type="media_karaoke_align")

    def get_or_create_media_lyrics_align_task(self, db: Session, media_item_id: int) -> ProcessingTask:
        """Return an existing active media lyrics alignment task or create one."""
        return self._get_or_create_media_task(db, media_item_id, task_type="media_lyrics_align")

    def create_media_vocal_sync_prepare_task(
        self,
        db: Session,
        media_item_id: int,
        *,
        source_kind: str = "youtube",
    ) -> ProcessingTask:
        """Create one active vocal-sync prepare task for a media item/source kind."""
        task_type = f"media_vocal_sync_prepare_{source_kind}"
        active = self.get_active_media_vocal_sync_prepare_task(db, media_item_id)
        if active is not None:
            raise ValueError("A vocal sync prepare task is already running for this media item")

        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise ValueError(f"Media item not found: {media_item_id}")
        task = ProcessingTask(
            task_type=task_type,
            source_kind=source_kind,
            target_media_item_id=media_item_id,
            status=ProcessingTaskStatus.PENDING.value,
            stage="queued",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def get_active_media_vocal_sync_prepare_task(
        self,
        db: Session,
        media_item_id: int,
    ) -> ProcessingTask | None:
        """Return the active vocal-sync prepare task for one media item, if any."""
        return (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.target_media_item_id == media_item_id,
                ProcessingTask.target_queue_item_id.is_(None),
                ProcessingTask.task_type.in_(self.VOCAL_SYNC_PREPARE_TASK_TYPES),
                ProcessingTask.status.in_(self.ACTIVE_STATUSES),
            )
            .order_by(ProcessingTask.updated_at.desc(), ProcessingTask.id.desc())
            .first()
        )

    def recent_media_vocal_sync_prepare_tasks(
        self,
        db: Session,
        media_item_id: int,
        *,
        limit: int = 25,
    ) -> list[ProcessingTask]:
        """Return recent vocal-sync prepare tasks for one media item."""
        return (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.target_media_item_id == media_item_id,
                ProcessingTask.target_queue_item_id.is_(None),
                ProcessingTask.task_type.in_(self.VOCAL_SYNC_PREPARE_TASK_TYPES),
            )
            .order_by(ProcessingTask.updated_at.desc(), ProcessingTask.id.desc())
            .limit(limit)
            .all()
        )

    def get_latest_terminal_media_vocal_sync_prepare_task(
        self,
        db: Session,
        media_item_id: int,
    ) -> ProcessingTask | None:
        """Return the latest failed or canceled vocal-sync prepare task for one media item."""
        return (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.target_media_item_id == media_item_id,
                ProcessingTask.target_queue_item_id.is_(None),
                ProcessingTask.task_type.in_(self.VOCAL_SYNC_PREPARE_TASK_TYPES),
                ProcessingTask.status.in_(
                    [
                        ProcessingTaskStatus.FAILED.value,
                        ProcessingTaskStatus.CANCELED.value,
                    ]
                ),
            )
            .order_by(ProcessingTask.updated_at.desc(), ProcessingTask.id.desc())
            .first()
        )

    def _get_or_create_media_task(
        self,
        db: Session,
        media_item_id: int,
        *,
        task_type: str,
    ) -> ProcessingTask:
        active = (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.target_media_item_id == media_item_id,
                ProcessingTask.target_queue_item_id.is_(None),
                ProcessingTask.task_type == task_type,
                ProcessingTask.status.in_(self.ACTIVE_STATUSES),
            )
            .order_by(ProcessingTask.id.desc())
            .first()
        )
        if active is not None:
            return active

        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise ValueError(f"Media item not found: {media_item_id}")
        task = ProcessingTask(
            task_type=task_type,
            source_kind="library_media" if not media_item.youtube_id else "uploaded_media",
            target_media_item_id=media_item_id,
            status=ProcessingTaskStatus.PENDING.value,
            stage="queued",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def list_tasks(
        self,
        db: Session,
        *,
        include_done: bool = False,
        include_failed: bool = True,
        limit: int = 25,
    ) -> list[ProcessingTaskResponse]:
        """List recent tasks enriched with current live state."""
        query = db.query(ProcessingTask)
        if include_done and include_failed:
            pass
        elif include_done:
            query = query.filter(
                ProcessingTask.status != ProcessingTaskStatus.FAILED.value
            )
        elif include_failed:
            query = query.filter(
                ProcessingTask.status != ProcessingTaskStatus.DONE.value
            )
        else:
            query = query.filter(ProcessingTask.status.in_(self.ACTIVE_STATUSES))
        tasks = (
            query.order_by(ProcessingTask.updated_at.desc(), ProcessingTask.id.desc())
            .limit(limit)
            .all()
        )
        return [self.to_response(task) for task in tasks]

    def get_task(self, db: Session, task_id: int) -> ProcessingTask | None:
        """Fetch one task row."""
        return db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()

    def to_response(self, task: ProcessingTask) -> ProcessingTaskResponse:
        """Map task row to response model with live state if available."""
        snapshot = task_stream_manager.snapshot_now(task.id)
        live = None
        if snapshot is not None:
            live = ProcessingTaskSnapshotResponse(
                progress_percent=snapshot.get("progress_percent"),
                progress_label=snapshot.get("progress_label"),
                progress_label_key=snapshot.get("progress_label_key"),
                progress_label_args=snapshot.get("progress_label_args"),
                progress_step_index=snapshot.get("progress_step_index"),
                progress_step_total=snapshot.get("progress_step_total"),
                event_sequence=snapshot.get("event_sequence", 0),
                event_count=snapshot.get("event_count", 0),
            )
        return ProcessingTaskResponse(
            id=task.id,
            task_type=task.task_type,
            source_kind=task.source_kind,
            target_queue_item_id=task.target_queue_item_id,
            target_media_item_id=task.target_media_item_id,
            status=ProcessingTaskStatus(task.status),
            stage=task.stage,
            attempt_count=task.attempt_count,
            last_error_summary=task.last_error_summary,
            last_error_detail=task.last_error_detail,
            started_at=task.started_at,
            finished_at=task.finished_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            live=live,
        )

    async def initialize_live_state(self, task: ProcessingTask):
        """Ensure a live stream entry exists for a durable task."""
        await task_stream_manager.ensure_task(
            task.id,
            status=task.status,
            stage=task.stage,
        )

    async def set_status(
        self,
        db: Session,
        task_id: int,
        *,
        status: ProcessingTaskStatus,
        stage: str | None = None,
        error_summary: str | None = None,
        error_detail: str | None = None,
        progress_label: str | None = None,
        progress_label_key: str | None = None,
        progress_label_args: dict[str, Any] | None = None,
        progress_percent: int | None = None,
        progress_step_index: int | None = None,
        progress_step_total: int | None = None,
    ) -> ProcessingTask:
        """Persist a durable task state change and publish it live."""
        task = self.get_task(db, task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")

        task.status = status.value
        if stage is not None:
            task.stage = stage
        if error_summary is not None:
            task.last_error_summary = error_summary
        if error_detail is not None:
            task.last_error_detail = error_detail
        now = utc_now_naive()
        task.updated_at = now
        if status in (
            ProcessingTaskStatus.DOWNLOADING,
            ProcessingTaskStatus.PROCESSING,
        ) and task.started_at is None:
            task.started_at = now
        if status in (ProcessingTaskStatus.DONE, ProcessingTaskStatus.FAILED):
            task.finished_at = now
        db.commit()
        db.refresh(task)

        await task_stream_manager.publish(
            task.id,
            event_type=(
                "status_changed"
                if status
                not in (
                    ProcessingTaskStatus.DONE,
                    ProcessingTaskStatus.FAILED,
                    ProcessingTaskStatus.CANCELED,
                )
                else (
                    "done"
                    if status == ProcessingTaskStatus.DONE
                    else ("error" if status == ProcessingTaskStatus.FAILED else "canceled")
                )
            ),
            status=task.status,
            stage=task.stage,
            progress_percent=progress_percent,
            progress_label=progress_label,
            progress_label_key=progress_label_key,
            progress_label_args=progress_label_args,
            progress_step_index=progress_step_index,
            progress_step_total=progress_step_total,
            message=error_summary,
            stream="system",
        )
        if status in (
            ProcessingTaskStatus.DONE,
            ProcessingTaskStatus.FAILED,
            ProcessingTaskStatus.CANCELED,
        ):
            await task_stream_manager.mark_task_terminal(task.id, status=task.status)
        await self._sync_queue_side_effects(db, task)
        return task

    async def set_stage(
        self,
        db: Session,
        task_id: int,
        *,
        status: ProcessingTaskStatus | None = None,
        stage: str,
        progress_label: str | None = None,
        progress_label_key: str | None = None,
        progress_label_args: dict[str, Any] | None = None,
        progress_percent: int | None = None,
        progress_step_index: int | None = None,
        progress_step_total: int | None = None,
    ) -> ProcessingTask:
        """Persist a stage change and publish it live."""
        task = self.get_task(db, task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        if status is not None:
            task.status = status.value
        task.stage = stage
        task.updated_at = utc_now_naive()
        if task.started_at is None and task.status in self.ACTIVE_STATUSES:
            task.started_at = utc_now_naive()
        db.commit()
        db.refresh(task)

        await task_stream_manager.publish(
            task.id,
            event_type="stage_changed",
            status=task.status,
            stage=stage,
            progress_percent=progress_percent,
            progress_label=progress_label,
            progress_label_key=progress_label_key,
            progress_label_args=progress_label_args,
            progress_step_index=progress_step_index,
            progress_step_total=progress_step_total,
            stream="system",
        )
        await self._sync_queue_side_effects(db, task)
        return task

    async def set_canceled(
        self,
        db: Session,
        task_id: int,
        *,
        stage: str | None = None,
        progress_label: str | None = None,
        progress_label_key: str | None = None,
        progress_label_args: dict[str, Any] | None = None,
    ) -> ProcessingTask:
        """Persist a canceled task state and publish it live."""
        task = self.get_task(db, task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        task.status = ProcessingTaskStatus.CANCELED.value
        if stage is not None:
            task.stage = stage
        task.last_error_summary = None
        task.last_error_detail = None
        task.updated_at = utc_now_naive()
        task.finished_at = task.finished_at or utc_now_naive()
        db.commit()
        db.refresh(task)

        await task_stream_manager.publish(
            task.id,
            event_type="canceled",
            status=task.status,
            stage=task.stage,
            progress_label=progress_label,
            progress_label_key=progress_label_key,
            progress_label_args=progress_label_args,
            stream="system",
        )
        await task_stream_manager.mark_task_terminal(task.id, status=task.status)
        return task

    async def emit_progress(
        self,
        task_id: int,
        *,
        queue_item_id: int | None = None,
        progress_percent: int | None = None,
        progress_label: str | None = None,
        progress_label_key: str | None = None,
        progress_label_args: dict[str, Any] | None = None,
        status: str | None = None,
        stage: str | None = None,
        progress_step_index: int | None = None,
        progress_step_total: int | None = None,
    ):
        """Publish live progress without writing SQLite."""
        await task_stream_manager.publish(
            task_id,
            event_type="progress",
            status=status,
            stage=stage,
            progress_percent=progress_percent,
            progress_label=progress_label,
            progress_label_key=progress_label_key,
            progress_label_args=progress_label_args,
            progress_step_index=progress_step_index,
            progress_step_total=progress_step_total,
            stream="system",
        )
        if queue_item_id is None:
            return

        from services.websocket_manager import manager

        await manager.broadcast_queue_item_progress(
            {
                "id": queue_item_id,
                "task_id": task_id,
                "status": status,
                "processing_stage": stage,
                "processing_progress": progress_percent,
                "processing_label": progress_label,
                "processing_label_key": progress_label_key,
                "processing_label_args": progress_label_args,
                "processing_step_index": progress_step_index,
                "processing_step_total": progress_step_total,
            }
        )

    async def emit_log(
        self,
        task_id: int,
        *,
        message: str,
        stream: str,
        status: str | None = None,
        stage: str | None = None,
        progress_percent: int | None = None,
        progress_label: str | None = None,
        progress_label_key: str | None = None,
        progress_label_args: dict[str, Any] | None = None,
        progress_step_index: int | None = None,
        progress_step_total: int | None = None,
    ):
        """Publish a live task log line without writing SQLite."""
        await task_stream_manager.publish(
            task_id,
            event_type="log",
            status=status,
            stage=stage,
            progress_percent=progress_percent,
            progress_label=progress_label,
            progress_label_key=progress_label_key,
            progress_label_args=progress_label_args,
            progress_step_index=progress_step_index,
            progress_step_total=progress_step_total,
            message=message,
            stream=stream,
        )

    async def cancel_task(
        self,
        db: Session,
        task_id: int,
    ) -> ProcessingTask:
        """Cancel a task and reset its queue/media state for retry."""
        task = self.get_task(db, task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")

        if task.status == ProcessingTaskStatus.CANCELED.value:
            await self._cancel_queue_and_media_side_effects(db, task)
            return task

        task.status = ProcessingTaskStatus.CANCELED.value
        task.last_error_summary = None
        task.last_error_detail = None
        task.updated_at = utc_now_naive()
        task.finished_at = task.finished_at or task.updated_at
        db.commit()
        db.refresh(task)

        await task_stream_manager.publish(
            task.id,
            event_type="canceled",
            status=task.status,
            stage=task.stage,
            stream="system",
        )
        await task_stream_manager.mark_task_terminal(task.id, status=task.status)
        await self._cancel_queue_and_media_side_effects(db, task)
        return task

    async def retry_task(
        self,
        db: Session,
        task_id: int,
    ) -> ProcessingTask:
        """Retry a failed task."""
        task = self.get_task(db, task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")

        if task.status != ProcessingTaskStatus.FAILED.value:
            raise ValueError("Only failed tasks can be retried")

        task.status = ProcessingTaskStatus.PENDING.value
        task.last_error_summary = None
        task.last_error_detail = None
        task.updated_at = utc_now_naive()
        db.commit()
        db.refresh(task)
        return task

    async def delete_canceled_task(self, db: Session, task_id: int) -> dict[str, int | None]:
        """Delete a canceled task and any orphaned rows it leaves behind."""
        task = self.get_task(db, task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        if task.status != ProcessingTaskStatus.CANCELED.value:
            raise ValueError("Only canceled tasks can be deleted")

        queue_item_id = task.target_queue_item_id
        media_item_id = self._task_media_id(db, task)
        deleted_media_item_id: int | None = None

        if queue_item_id is not None:
            queue_item = (
                db.query(QueueItem)
                .filter(QueueItem.id == queue_item_id)
                .first()
            )
            if queue_item is not None:
                db.delete(queue_item)
                db.flush()

        if media_item_id is not None:
            media_item = (
                db.query(MediaItem)
                .filter(MediaItem.id == media_item_id)
                .first()
            )
            if media_item is not None:
                remaining_queue_items = (
                    db.query(QueueItem.id)
                    .filter(QueueItem.media_id == media_item_id)
                    .count()
                )
                remaining_active_tasks = (
                    db.query(ProcessingTask.id)
                    .filter(
                        ProcessingTask.target_media_item_id == media_item_id,
                        ProcessingTask.status != ProcessingTaskStatus.CANCELED.value,
                        ProcessingTask.id != task_id,
                    )
                    .count()
                )
                if media_item.missing and remaining_queue_items == 0 and remaining_active_tasks == 0:
                    MediaLibraryMaintenanceService().delete_media_item(db, media_item_id)
                    deleted_media_item_id = media_item_id

        if db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first() is not None:
            db.delete(task)
            db.commit()
        else:
            db.commit()

        return {
            "deleted_task_id": task_id,
            "deleted_queue_item_id": queue_item_id,
            "deleted_media_item_id": deleted_media_item_id,
        }

    def recover_interrupted_tasks(self, db: Session) -> list[int]:
        """Reset interrupted tasks to pending and return ids for restart."""
        tasks = (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.status.in_(
                    [
                        ProcessingTaskStatus.PENDING.value,
                        ProcessingTaskStatus.DOWNLOADING.value,
                        ProcessingTaskStatus.PROCESSING.value,
                    ]
                )
            )
            .order_by(ProcessingTask.id.asc())
            .all()
        )
        task_ids = []
        for task in tasks:
            task.status = ProcessingTaskStatus.PENDING.value
            task.stage = task.stage or "queued"
            task.attempt_count = int(task.attempt_count or 0) + 1
            task.last_error_summary = None
            task.last_error_detail = None
            task.finished_at = None
            task.updated_at = utc_now_naive()
            task_ids.append(task.id)
        if task_ids:
            db.commit()
        return task_ids
    
    def can_retry_task(
        self,
        db: Session,
        task: ProcessingTask,
        *,
        is_admin: bool = False,
        requester_id: str | None = None,
    ) -> bool:
        """Return whether the current viewer may retry the task."""
        if is_admin:
            return True
        if task.status != ProcessingTaskStatus.FAILED.value:
            return False
        if task.target_queue_item_id is None:
            return False
        queue_item = (
            db.query(QueueItem)
            .filter(QueueItem.id == task.target_queue_item_id)
            .first()
        )
        if queue_item is None:
            return False
        return True

    def can_cancel_task(
        self,
        db: Session,
        task: ProcessingTask,
        *,
        is_admin: bool = False,
        requester_id: str | None = None,
    ) -> bool:
        """Return whether the current viewer may cancel the task."""
        if is_admin:
            return True
        if task.status not in self.CANCELLABLE_STATUSES:
            return False
        if task.target_queue_item_id is None:
            return False
        normalized_requester_id = self._normalize_optional_id(requester_id)
        if normalized_requester_id is None:
            return False
        queue_item = (
            db.query(QueueItem)
            .filter(QueueItem.id == task.target_queue_item_id)
            .first()
        )
        if queue_item is None:
            return False
        return self._normalize_optional_id(queue_item.user_id) == normalized_requester_id

    def get_cancelable_task_ids(
        self,
        db: Session,
        task: ProcessingTask,
        *,
        is_admin: bool = False,
        requester_id: str | None = None,
    ) -> list[int]:
        """Return task ids that should be canceled together for this request."""
        if not self.can_cancel_task(db, task, is_admin=is_admin, requester_id=requester_id):
            return []

        media_id = self._task_media_id(db, task)
        task_ids = [task.id]
        if media_id is None:
            return task_ids

        query = (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.target_media_item_id == media_id,
                ProcessingTask.status.in_(self.CANCELLABLE_STATUSES),
            )
            .order_by(ProcessingTask.id.asc())
        )
        related_tasks = query.all()
        if is_admin:
            for related_task in related_tasks:
                if related_task.id != task.id:
                    task_ids.append(related_task.id)
            return task_ids

        normalized_requester_id = self._normalize_optional_id(requester_id)
        if normalized_requester_id is None:
            return []

        for related_task in related_tasks:
            if related_task.id == task.id:
                continue
            if related_task.target_queue_item_id is None:
                continue
            queue_item = (
                db.query(QueueItem)
                .filter(QueueItem.id == related_task.target_queue_item_id)
                .first()
            )
            if queue_item is None:
                continue
            if self._normalize_optional_id(queue_item.user_id) == normalized_requester_id:
                task_ids.append(related_task.id)
        return task_ids

    def restartable_task_ids(self, db: Session) -> list[int]:
        """Return pending task ids in restart order."""
        tasks = (
            db.query(ProcessingTask.id)
            .filter(ProcessingTask.status == ProcessingTaskStatus.PENDING.value)
            .order_by(ProcessingTask.created_at.asc(), ProcessingTask.id.asc())
            .all()
        )
        return [task_id for (task_id,) in tasks]

    def _mirror_queue_status(self, db: Session, task: ProcessingTask) -> QueueItem | None:
        """Keep queue_item.status compatible with the durable task state."""
        if task.target_queue_item_id is None:
            return None
        queue_item = (
            db.query(QueueItem)
            .filter(QueueItem.id == task.target_queue_item_id)
            .first()
        )
        if queue_item is None:
            return None

        if task.status == ProcessingTaskStatus.PENDING.value:
            queue_item.status = QueueStatus.PENDING.value
        elif task.status == ProcessingTaskStatus.DOWNLOADING.value:
            queue_item.status = QueueStatus.DOWNLOADING.value
        elif task.status == ProcessingTaskStatus.PROCESSING.value:
            queue_item.status = QueueStatus.PROCESSING.value
        elif task.status == ProcessingTaskStatus.DONE.value:
            queue_item.status = QueueStatus.READY.value
        elif task.status == ProcessingTaskStatus.FAILED.value:
            queue_item.status = QueueStatus.FAILED.value
            queue_item.error = task.last_error_summary
        elif task.status == ProcessingTaskStatus.CANCELED.value:
            queue_item.status = QueueStatus.PENDING.value
            queue_item.error = None
        db.commit()
        db.refresh(queue_item)
        return queue_item

    def _task_media_id(self, db: Session, task: ProcessingTask) -> int | None:
        if task.target_media_item_id is not None:
            return task.target_media_item_id
        if task.target_queue_item_id is None:
            return None
        queue_item = (
            db.query(QueueItem)
            .filter(QueueItem.id == task.target_queue_item_id)
            .first()
        )
        if queue_item is None:
            return None
        return queue_item.media_id

    async def _sync_queue_side_effects(self, db: Session, task: ProcessingTask):
        """Broadcast queue changes after task persistence and mirroring."""
        queue_item = self._mirror_queue_status(db, task)
        if queue_item is None:
            return

        from services.queue_service import QueueService
        from services.websocket_manager import manager

        queue_service = QueueService()
        response = queue_service._to_response(queue_item)
        if task.status == ProcessingTaskStatus.FAILED.value and task.last_error_summary:
            await manager.broadcast_queue_item_failed(queue_item.id, task.last_error_summary)
        else:
            await manager.broadcast_queue_item_updated(response.model_dump(mode="json"))

        if task.status == ProcessingTaskStatus.DONE.value:
            promoted = queue_service.promote_next_ready_if_idle(db)
            if promoted:
                await manager.broadcast_current_item_changed(promoted.id, None)

    async def _cancel_queue_and_media_side_effects(
        self,
        db: Session,
        task: ProcessingTask,
    ) -> None:
        """Reset queue/media rows and delete generated files for a canceled task."""
        from services.karaoke_service import KaraokeService

        karaoke_service = KaraokeService()
        karaoke_service.cleanup_canceled_task(db, task)
        await self._sync_cancel_side_effects(db, task)

    async def _sync_cancel_side_effects(self, db: Session, task: ProcessingTask) -> None:
        """Broadcast queue changes after a task cancel/reset."""
        queue_item = self._mirror_queue_status(db, task)
        if queue_item is None:
            return

        from services.queue_service import QueueService
        from services.websocket_manager import manager

        queue_service = QueueService()
        response = queue_service._to_response(queue_item)
        await manager.broadcast_queue_item_updated(response.model_dump(mode="json"))

    @staticmethod
    def _normalize_optional_id(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None

class TaskExecutionCoordinator:
    """Start processing tasks in background threads without duplicate runners."""

    def __init__(self):
        self._active_task_ids: set[int] = set()
        self._task_contexts: dict[int, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self, task_id: int):
        """Start a background worker for the task if one is not already running."""
        with self._lock:
            if task_id in self._active_task_ids:
                return
            self._active_task_ids.add(task_id)
            cancel_event = threading.Event()
            self._task_contexts[task_id] = {
                "cancel_event": cancel_event,
                "loop": None,
                "task": None,
            }
        thread = threading.Thread(
            target=self._run_task,
            args=(task_id,),
            daemon=True,
            name=f"processing-task-{task_id}",
        )
        thread.start()

    def _run_task(self, task_id: int):
        from services.karaoke_service import KaraokeService

        db = SessionLocal()
        loop = asyncio.new_event_loop()
        cancel_event = None
        try:
            asyncio.set_event_loop(loop)
            with self._lock:
                context = self._task_contexts.get(task_id)
                if context is not None:
                    context["loop"] = loop
                    cancel_event = context["cancel_event"]
            coroutine = KaraokeService().process_task(
                db,
                task_id,
                cancel_event=cancel_event,
            )
            task = loop.create_task(coroutine)
            with self._lock:
                context = self._task_contexts.get(task_id)
                if context is not None:
                    context["task"] = task
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            logger.info("Background processing task canceled task_id=%s", task_id)
        except Exception:
            logger.exception("Background processing task crashed task_id=%s", task_id)
        finally:
            try:
                if not loop.is_closed():
                    loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()
                asyncio.set_event_loop(None)
            db.close()
            with self._lock:
                self._active_task_ids.discard(task_id)
                self._task_contexts.pop(task_id, None)

    def cancel(self, task_id: int) -> bool:
        """Request cooperative cancellation for a running or queued task."""
        with self._lock:
            context = self._task_contexts.get(task_id)
            if context is None:
                return False
            cancel_event = context.get("cancel_event")
            if isinstance(cancel_event, threading.Event):
                cancel_event.set()
            return True

    def cancel_many(self, task_ids: list[int]) -> list[int]:
        """Request cancellation for multiple tasks."""
        canceled_task_ids: list[int] = []
        for task_id in task_ids:
            if self.cancel(task_id):
                canceled_task_ids.append(task_id)
        return canceled_task_ids

    def cancel_event_for(self, task_id: int) -> threading.Event | None:
        """Return the cancellation event for an active task, if any."""
        with self._lock:
            context = self._task_contexts.get(task_id)
            if context is None:
                return None
            cancel_event = context.get("cancel_event")
            return cancel_event if isinstance(cancel_event, threading.Event) else None
        
    def retry(self, task_id: int):
        """Retry a task by canceling it and starting a new execution."""
        self.cancel(task_id)
        self.start(task_id)


processing_task_service = ProcessingTaskService()
task_execution_coordinator = TaskExecutionCoordinator()
