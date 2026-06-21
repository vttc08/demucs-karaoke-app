"""API routes for adding guide vocals to existing media."""
from __future__ import annotations

import logging
import subprocess

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from routes.auth import require_admin_user
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


@router.post("/prepare-youtube")
async def prepare_vocals_from_youtube(
    item_id: int,
    payload: VocalSyncYoutubePrepareRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Download a vocal source from YouTube, separate it, and estimate the offset."""
    try:
        session = await vocal_sync_service.prepare_from_youtube(
            db,
            item_id,
            payload.youtube_id.strip(),
        )
        return {"status": "ready", "session": session.to_dict()}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
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
        session = await vocal_sync_service.prepare_from_upload(
            db,
            item_id,
            source_filename=file.filename or "source",
            source_file=file.file,
        )
        return {"status": "ready", "session": session.to_dict()}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
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
    _admin=Depends(require_admin_user),
):
    """Delete a prepared review session and its cache artifacts."""
    try:
        session = vocal_sync_service.get_session(session_id)
        if session.media_item_id != item_id:
            raise VocalSyncConflictError("Vocal sync session does not match media item")
        vocal_sync_service.delete_session(session_id)
        return {"status": "ok"}
    except VocalSyncNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VocalSyncConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

