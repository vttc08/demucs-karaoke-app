"""API routes for media library maintenance operations."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.media_library_maintenance_service import (
    MediaItemDeleteConflictError,
    MediaItemNotFoundError,
    MediaLibraryMaintenanceService,
    MediaItemRenameConflictError,
)
from services.media_library_sync_service import MediaLibrarySyncService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media", tags=["media-library"])
media_library_sync_service = MediaLibrarySyncService()
media_library_maintenance_service = MediaLibraryMaintenanceService()


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
