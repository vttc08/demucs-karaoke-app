"""API routes for media library maintenance operations."""
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import MediaItem
from services.media_library_maintenance_service import (
    MediaItemDeleteConflictError,
    MediaItemNotFoundError,
    MediaLibraryMaintenanceService,
    MediaItemRenameConflictError,
)
from services.media_library_sync_service import MediaLibrarySyncService
from services.media_naming import build_media_stem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media", tags=["media-library"])
media_library_sync_service = MediaLibrarySyncService()
media_library_maintenance_service = MediaLibraryMaintenanceService()


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str = Form(None),
    ai_process: bool = Form(False),
    sync_lyrics: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Upload a new media file and create a library entry."""
    # 1. Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in [".mp3", ".mp4"]:
        raise HTTPException(status_code=400, detail="Only .mp3 and .mp4 files are supported")

    # 2. Build filename
    stem = build_media_stem(title, artist)
    # Ensure stem is unique
    final_stem = stem
    counter = 1
    while (settings.media_path / f"{final_stem}{ext}").exists():
        final_stem = f"{stem}_{counter}"
        counter += 1
    
    filename = f"{final_stem}{ext}"
    target_path = settings.media_path / filename
    
    # 3. Save file
    try:
        settings.media_path.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        logger.exception("Failed to save uploaded file: %s", filename)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(exc)}")

    # 4. Create database entry
    media_item = MediaItem(
        title=title,
        artist=artist,
        file_stem=final_stem,
        media_path=f"media/{filename}",
        missing=False,
    )
    db.add(media_item)
    db.commit()
    db.refresh(media_item)

    # Note: AI process and Sync Lyrics could be triggered here or as a background task.
    # For now, we just acknowledge they were requested.
    logger.info(
        "Media uploaded: id=%s title=%s artist=%s ai_process=%s sync_lyrics=%s",
        media_item.id, title, artist, ai_process, sync_lyrics
    )

    return {
        "status": "ok",
        "media_id": media_item.id,
        "filename": filename,
        "processing_requested": {"ai": ai_process, "lyrics": sync_lyrics}
    }


@router.post("/scan")
def scan_media_library(db: Session = Depends(get_db)):
    """Run an on-demand filesystem sync for media library rows."""
    summary = media_library_sync_service.scan_library(db)
    return {"status": "ok", "summary": summary}


@router.delete("/{item_id}")
def delete_media_item(item_id: int, db: Session = Depends(get_db)):
    """Delete a media item and its on-disk files."""
    try:
        summary = media_library_maintenance_service.delete_media_item(db, item_id)
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaItemDeleteConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Failed to delete media item media_id=%s", item_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", "summary": summary}


@router.patch("/{item_id}")
def rename_media_item(item_id: int, payload: dict, db: Session = Depends(get_db)):
    """Rename a media item in the database, and optionally on disk."""
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise HTTPException(status_code=400, detail="title is required")

    artist = payload.get("artist")
    if artist is not None and not isinstance(artist, str):
        raise HTTPException(status_code=400, detail="artist must be a string or null")

    rename_on_disk = payload.get("rename_on_disk")
    if not isinstance(rename_on_disk, bool):
        raise HTTPException(status_code=400, detail="rename_on_disk must be a boolean")

    try:
        summary = media_library_maintenance_service.rename_media_item(
            db,
            item_id,
            title=title,
            artist=artist,
            rename_on_disk=rename_on_disk,
        )
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaItemRenameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Failed to rename media item media_id=%s", item_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "ok", "summary": summary}
