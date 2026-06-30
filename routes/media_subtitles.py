"""API routes for the subtitle editor workflow."""
from __future__ import annotations

from dataclasses import asdict
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from routes.auth import require_admin_user
from services.subtitle_editor_service import subtitle_editor_service
from services.subtitle_workflow_service import (
    SubtitleWorkflowConflictError,
    SubtitleWorkflowNotFoundError,
    subtitle_workflow_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media/{item_id}/subtitles", tags=["subtitles"])


class SubtitleEditorProcessRequest(BaseModel):
    max_line_length: int = Field(default=36, ge=1, le=200)
    max_line_length_cjk: int = Field(default=12, ge=1, le=100)


class SubtitleEditorSaveRequest(BaseModel):
    segments: list[dict] = Field(default_factory=list)


def _subtitle_download_response(content: str, filename: str) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


@router.get("/json")
def load_subtitle_json(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Load the normalized synced JSON lyrics for the split/merge editor."""
    try:
        payload = subtitle_editor_service.load_editor_payload(db, item_id)
        return asdict(payload)
    except SubtitleWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubtitleWorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/process")
def process_subtitle_json(
    item_id: int,
    request: SubtitleEditorProcessRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Rewrap the persisted synced JSON lyrics with deterministic line splitting."""
    try:
        segments = subtitle_editor_service.process_saved_segments(
            db,
            item_id,
            max_line_length=request.max_line_length,
            max_line_length_cjk=request.max_line_length_cjk,
        )
        return {
            "status": "ok",
            "media_id": item_id,
            "segments": segments,
        }
    except SubtitleWorkflowConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/save")
def save_subtitle_json(
    item_id: int,
    request: SubtitleEditorSaveRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Persist edited synced JSON lyrics back to the media sidecar."""
    try:
        payload = subtitle_editor_service.save_segments(db, item_id, request.segments)
        return asdict(payload)
    except SubtitleWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubtitleWorkflowConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
