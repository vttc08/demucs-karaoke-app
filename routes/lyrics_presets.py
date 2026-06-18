"""API routes for shared lyric preset CRUD."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import LyricsPresetCreateRequest, LyricsPresetResponse, LyricsPresetUpdateRequest
from routes.auth import require_admin_user
from services.lyrics_preset_service import (
    LyricsPresetConflictError,
    LyricsPresetNotFoundError,
    LyricsPresetValidationError,
    lyrics_preset_service,
)

router = APIRouter(prefix="/api/lyrics-presets", tags=["lyrics-presets"])


@router.get("/", response_model=list[LyricsPresetResponse])
def list_lyrics_presets(
    _admin=Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Return all shared lyric presets."""
    return lyrics_preset_service.list_presets(db)


@router.post("/", response_model=LyricsPresetResponse)
def create_lyrics_preset(
    payload: LyricsPresetCreateRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Create a new shared lyric preset."""
    try:
        return lyrics_preset_service.create_preset(db, payload)
    except LyricsPresetValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LyricsPresetConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{preset_id}", response_model=LyricsPresetResponse)
def get_lyrics_preset(
    preset_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Return a single lyric preset."""
    try:
        return lyrics_preset_service.get_preset(db, preset_id)
    except LyricsPresetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{preset_id}", response_model=LyricsPresetResponse)
def update_lyrics_preset(
    preset_id: int,
    payload: LyricsPresetUpdateRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Update an existing lyric preset."""
    try:
        return lyrics_preset_service.update_preset(db, preset_id, payload)
    except LyricsPresetValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LyricsPresetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LyricsPresetConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{preset_id}")
def delete_lyrics_preset(
    preset_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Delete a lyric preset."""
    try:
        lyrics_preset_service.delete_preset(db, preset_id)
    except LyricsPresetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok"}
