"""API routes for adding guide vocals to existing media."""
from __future__ import annotations

import logging
import subprocess

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import MediaItem
from routes.auth import require_admin_user
from services.processing_task_service import processing_task_service, task_execution_coordinator
from services.vocal_sync_service import (
    VocalSyncConflictError,
    VocalSyncError,
    VocalSyncNotFoundError,
    VocalSyncService,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media/{item_id}/vocals-sync", tags=["vocal-sync"])
vocal_sync_service = VocalSyncService()


class VocalSyncYoutubePrepareRequest(BaseModel):
    youtube_id: str = Field(min_length=11, max_length=64)


class VocalSyncCommitRequest(BaseModel):
    offset_seconds: float


def _task_payload(task) -> dict:
    return processing_task_service.to_response(task).model_dump(mode="json")


def _ready_review(db: Session, item_id: int):
    return vocal_sync_service.latest_ready_review_for_media(
        db,
        item_id,
        task_types=processing_task_service.VOCAL_SYNC_PREPARE_TASK_TYPES,
    )


def _raise_prepare_conflict_if_needed(db: Session, item_id: int) -> None:
    active_task = processing_task_service.get_active_media_vocal_sync_prepare_task(db, item_id)
    if active_task is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "A vocal sync prepare task is already running for this media item",
                "status": "preparing",
                "existing_task_id": active_task.id,
            },
        )
    ready = _ready_review(db, item_id)
    if ready is not None:
        task, session = ready
        raise HTTPException(
            status_code=409,
            detail={
                "message": "A vocal sync review is already ready for this media item",
                "status": "ready",
                "existing_task_id": task.id,
                "existing_session_id": session.session_id,
            },
        )


@router.get("/status")
def get_vocal_sync_status(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Return the current durable vocal-sync state for one media item."""
    media_item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
    if media_item is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    if media_item.vocals_path and media_item.vocals_path.strip():
        return {"status": "has_vocals", "task": None, "session": None, "message": None}
    if media_item.missing:
        raise HTTPException(status_code=404, detail="Media item file is missing")

    active_task = processing_task_service.get_active_media_vocal_sync_prepare_task(db, item_id)
    if active_task is not None:
        return {
            "status": "preparing",
            "task": _task_payload(active_task),
            "session": None,
            "message": None,
        }

    ready = _ready_review(db, item_id)
    if ready is not None:
        task, session = ready
        return {
            "status": "ready",
            "task": _task_payload(task),
            "session": session.to_dict(),
            "message": None,
        }

    terminal_task = processing_task_service.get_latest_terminal_media_vocal_sync_prepare_task(db, item_id)
    if terminal_task is not None:
        return {
            "status": terminal_task.status,
            "task": _task_payload(terminal_task),
            "session": None,
            "message": terminal_task.last_error_summary,
        }

    return {"status": "idle", "task": None, "session": None, "message": None}


@router.post("/prepare-youtube")
async def prepare_vocals_from_youtube(
    item_id: int,
    payload: VocalSyncYoutubePrepareRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Download a vocal source from YouTube, separate it, and estimate the offset."""
    try:
        vocal_sync_service.validate_media_item_for_prepare(db, item_id)
        _raise_prepare_conflict_if_needed(db, item_id)
        task = processing_task_service.create_media_vocal_sync_prepare_task(db, item_id)
        vocal_sync_service.create_youtube_prepare_task_manifest(
            task.id,
            media_item_id=item_id,
            youtube_id=payload.youtube_id.strip(),
        )
        task_execution_coordinator.start(task.id)
        return {"status": "processing", "task_id": task.id}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VocalSyncError, subprocess.SubprocessError, OSError) as exc:
        logger.exception("Vocal sync YouTube preparation failed media_id=%s", item_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/prepare-upload")
async def prepare_vocals_from_upload(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Prepare guide vocals from an uploaded unseparated source file."""
    try:
        vocal_sync_service.validate_media_item_for_prepare(db, item_id)
        _raise_prepare_conflict_if_needed(db, item_id)
        task = processing_task_service.create_media_vocal_sync_prepare_task(db, item_id, source_kind="upload")
        vocal_sync_service.create_upload_prepare_task_manifest(
            task.id,
            media_item_id=item_id,
            source_filename=file.filename or "source",
            source_file=file.file,
        )
        task_execution_coordinator.start(task.id)
        return {"status": "processing", "task_id": task.id}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VocalSyncError, subprocess.SubprocessError, OSError) as exc:
        logger.exception("Vocal sync upload preparation failed media_id=%s", item_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sessions/{session_id}")
def get_vocal_sync_session(
    item_id: int,
    session_id: str,
    _admin=Depends(require_admin_user),
):
    """Return a prepared review session."""
    try:
        session = vocal_sync_service.get_session(session_id)
        if session.media_item_id != item_id:
            raise VocalSyncConflictError("Vocal sync session does not match media item")
        return {"status": "ready", "session": session.to_dict()}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VocalSyncError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/session")
def get_vocal_sync_session_for_task(
    item_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Return the prepared review session associated with a completed vocal-sync task."""
    try:
        task = processing_task_service.get_task(db, task_id)
        if task is None:
            raise VocalSyncNotFoundError("Vocal sync task not found")
        if int(task.target_media_item_id or 0) != int(item_id):
            raise VocalSyncConflictError("Vocal sync task does not match media item")
        manifest = vocal_sync_service.read_task_manifest(task_id)
        session_id = str(manifest.get("session_id") or "").strip()
        if not session_id:
            raise VocalSyncNotFoundError("Prepared vocal sync session is not ready")
        session = vocal_sync_service.get_session(session_id)
        return {"status": "ready", "session": session.to_dict()}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VocalSyncError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/commit")
def commit_vocal_sync_session(
    item_id: int,
    session_id: str,
    payload: VocalSyncCommitRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Commit the adjusted offset as the media item's guide-vocal sidecar."""
    try:
        session = vocal_sync_service.commit_session(
            db,
            item_id,
            session_id,
            payload.offset_seconds,
        )
        return {"status": "ok", "session": session.to_dict()}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (VocalSyncError, subprocess.SubprocessError, OSError) as exc:
        logger.exception("Vocal sync commit failed media_id=%s session_id=%s", item_id, session_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}")
def delete_vocal_sync_session(
    item_id: int,
    session_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Delete a prepared review session and its cache artifacts."""
    try:
        vocal_sync_service.delete_review_session(db, item_id, session_id)
        return {"status": "ok"}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
