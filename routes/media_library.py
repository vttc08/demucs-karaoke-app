"""API routes for media library maintenance operations."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.media_library_sync_service import MediaLibrarySyncService

router = APIRouter(prefix="/api/media", tags=["media-library"])
media_library_sync_service = MediaLibrarySyncService()


@router.post("/scan")
def scan_media_library(db: Session = Depends(get_db)):
    """Run an on-demand filesystem sync for media library rows."""
    summary = media_library_sync_service.scan_library(db)
    return {"status": "ok", "summary": summary}
