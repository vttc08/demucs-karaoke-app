"""API routes for the subtitle editor workflow."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from routes.auth import require_admin_user
from services.subtitle_workflow_service import (
    SubtitleWorkflowConflictError,
    SubtitleWorkflowNotFoundError,
    subtitle_workflow_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media/{item_id}/subtitles", tags=["subtitles"])


def _subtitle_download_response(content: str, filename: str) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


@router.get("/ass")
def export_ass(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Download an ASS subtitle export for the current JSON lyrics."""
    try:
        content, filename, _preview = subtitle_workflow_service.build_export_text(db, item_id, "ass")
        return _subtitle_download_response(content, filename)
    except SubtitleWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubtitleWorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/srt")
def export_srt(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Download an SRT subtitle export for the current JSON lyrics."""
    try:
        content, filename, _preview = subtitle_workflow_service.build_export_text(db, item_id, "srt")
        return _subtitle_download_response(content, filename)
    except SubtitleWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubtitleWorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/preview")
async def preview_subtitles(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Parse an edited subtitle upload and return overlap warnings before commit."""
    try:
        return subtitle_workflow_service.preview_upload(db, item_id, file)
    except SubtitleWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubtitleWorkflowConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Subtitle preview failed media_id=%s filename=%s", item_id, file.filename)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/upload")
async def upload_subtitles(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Replace the current JSON lyrics sidecar with an edited subtitle upload."""
    try:
        return subtitle_workflow_service.replace_from_upload(db, item_id, file)
    except SubtitleWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubtitleWorkflowConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Subtitle upload failed media_id=%s filename=%s", item_id, file.filename)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/raw-upload")
async def upload_raw_lyrics(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Replace the current lyrics sidecar with a raw .txt, .lrc, or .json upload."""
    try:
        return subtitle_workflow_service.replace_raw_upload(db, item_id, file)
    except SubtitleWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubtitleWorkflowConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Subtitle raw upload failed media_id=%s filename=%s", item_id, file.filename)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
