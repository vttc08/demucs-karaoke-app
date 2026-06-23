"""API routes for durable processing tasks and live SSE streams."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import ProcessingTaskResponse
from routes.auth import get_admin_user, require_admin_user
from services.processing_task_service import processing_task_service
from services.task_stream_service import task_stream_manager
from services.processing_task_service import task_execution_coordinator

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _current_guest_id(request: Request) -> str | None:
    guest_id = request.cookies.get("karaoke_guest_id")
    if guest_id is None:
        return None
    cleaned = " ".join(guest_id.split()).strip()
    return cleaned or None


def _serialize_sse(payload: dict) -> str:
    encoded = json.dumps(payload, default=str, separators=(",", ":"))
    return f"data: {encoded}\n\n"


@router.get("/", response_model=list[ProcessingTaskResponse])
def list_tasks(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """List active and recently failed tasks."""
    return processing_task_service.list_tasks(
        db,
        include_done=False,
        include_failed=True,
        limit=50,
    )


@router.get("/stream")
async def stream_task_summaries(_admin=Depends(require_admin_user)):
    """Stream live summary events for all tasks."""
    subscriber = await task_stream_manager.register_summary_subscriber()

    async def event_generator():
        try:
            snapshots = task_stream_manager.active_summaries_now()
            yield _serialize_sse({"event_type": "snapshot", "tasks": snapshots})
            while True:
                try:
                    payload = await asyncio.wait_for(subscriber.get(), timeout=15)
                    yield _serialize_sse(payload)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            await task_stream_manager.unregister_summary_subscriber(subscriber)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{task_id}", response_model=ProcessingTaskResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Get one durable task."""
    task = processing_task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return processing_task_service.to_response(task)

@router.post("/{task_id}/retry", response_model=ProcessingTaskResponse)
async def retry_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Retry a failed task."""
    task = processing_task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    is_admin = get_admin_user(request, db) is not None
    requester_id = _current_guest_id(request)

    if not processing_task_service.can_retry_task(
        db,
        task,
        is_admin=is_admin,
        requester_id=requester_id,
    ):
        raise HTTPException(status_code=403, detail="Not allowed to retry this task")
    
    task_execution_coordinator.retry(task_id)
    await processing_task_service.retry_task(db, task_id)
    return processing_task_service.to_response(task)


@router.post("/{task_id}/cancel", response_model=ProcessingTaskResponse)
async def cancel_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Cancel a durable task and reset its associated queue/media state."""
    task = processing_task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    is_admin = get_admin_user(request, db) is not None
    requester_id = _current_guest_id(request)
    if not processing_task_service.can_cancel_task(
        db,
        task,
        is_admin=is_admin,
        requester_id=requester_id,
    ):
        raise HTTPException(status_code=403, detail="Not allowed to cancel this task")

    task_ids = processing_task_service.get_cancelable_task_ids(
        db,
        task,
        is_admin=is_admin,
        requester_id=requester_id,
    )
    if not task_ids:
        raise HTTPException(status_code=403, detail="Not allowed to cancel this task")

    task_execution_coordinator.cancel_many(task_ids)
    for candidate_id in task_ids:
        if processing_task_service.get_task(db, candidate_id) is None:
            continue
        await processing_task_service.cancel_task(db, candidate_id)

    result = processing_task_service.get_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return processing_task_service.to_response(result)


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a canceled task and remove any orphaned rows it leaves behind."""
    task = processing_task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    is_admin = get_admin_user(request, db) is not None
    if not is_admin:
        raise HTTPException(status_code=403, detail="Not allowed to delete this task")
    if task.status != "canceled":
        raise HTTPException(status_code=409, detail="Only canceled tasks can be deleted")

    deleted = await processing_task_service.delete_canceled_task(db, task_id)
    await task_stream_manager.clear_task(task_id)
    if deleted.get("deleted_queue_item_id") is not None:
        from services.websocket_manager import manager

        await manager.broadcast_queue_item_removed(int(deleted["deleted_queue_item_id"]))
    return deleted


@router.get("/{task_id}/stream")
async def stream_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Stream live events for one task."""
    snapshot = task_stream_manager.snapshot_now(task_id)
    if snapshot is None and processing_task_service.get_task(db, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    subscriber = await task_stream_manager.register_task_subscriber(task_id)

    async def event_generator():
        try:
            current_snapshot = task_stream_manager.snapshot_now(task_id)
            if current_snapshot is not None:
                yield _serialize_sse(
                    {
                        "task_id": task_id,
                        "event_type": "snapshot",
                        "status": current_snapshot.get("status"),
                        "stage": current_snapshot.get("stage"),
                        "progress_percent": current_snapshot.get("progress_percent"),
                        "progress_label": current_snapshot.get("progress_label"),
                        "progress_label_key": current_snapshot.get("progress_label_key"),
                        "progress_label_args": current_snapshot.get("progress_label_args"),
                        "progress_step_index": current_snapshot.get("progress_step_index"),
                        "progress_step_total": current_snapshot.get("progress_step_total"),
                        "sequence": current_snapshot.get("event_sequence", 0),
                    }
                )
            for event in await task_stream_manager.recent_events(task_id):
                yield _serialize_sse(event)
            while True:
                try:
                    payload = await asyncio.wait_for(subscriber.get(), timeout=15)
                    yield _serialize_sse(payload)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            await task_stream_manager.unregister_task_subscriber(task_id, subscriber)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
