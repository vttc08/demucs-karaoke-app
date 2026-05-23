"""API routes for durable processing tasks and live SSE streams."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import ProcessingTaskResponse
from routes.auth import require_admin_user
from services.processing_task_service import processing_task_service
from services.task_stream_service import task_stream_manager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


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
