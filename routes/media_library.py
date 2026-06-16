"""API routes for media library maintenance operations."""

import json
import logging
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import MediaItem, MediaTrimRequest, QueueItemCreate
from routes.auth import require_admin_user
from services.media_library_maintenance_service import (
    MediaItemDeleteConflictError,
    MediaItemNotFoundError,
    MediaLibraryMaintenanceService,
    MediaItemRenameConflictError,
)
from services.media_library_sync_service import MediaLibrarySyncService
from services.media_naming import build_media_stem
from services.media_thumbnail_service import MediaThumbnailService
from services.media_trim_service import (
    MediaTrimConflictError,
    MediaTrimError,
    MediaTrimNotFoundError,
    MediaTrimService,
    MediaTrimUnsupportedError,
)
from services.processing_task_service import processing_task_service, task_execution_coordinator
from services.queue_service import QueueService
from services.runtime_settings_service import RuntimeSettingsService
from services.websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media", tags=["media-library"])
media_library_sync_service = MediaLibrarySyncService()
media_library_maintenance_service = MediaLibraryMaintenanceService()
media_thumbnail_service = MediaThumbnailService()
queue_service = QueueService()
runtime_settings_service = RuntimeSettingsService()
media_trim_service = MediaTrimService()
_UPLOAD_EXTENSIONS = {".mp3", ".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v"}


@router.get("/{item_id}/trim-info")
def get_media_trim_info(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Return timing and sidecar metadata for the lossless trim editor."""
    try:
        return media_trim_service.get_trim_info(db, item_id)
    except MediaTrimNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (MediaTrimError, OSError, ValueError) as exc:
        logger.exception("Failed to inspect media trim data media_id=%s", item_id)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{item_id}/trim")
def trim_media_item(
    item_id: int,
    payload: MediaTrimRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Destructively replace a media item with a synchronized lossless trim."""
    try:
        summary = media_trim_service.trim_media_item(
            db,
            item_id,
            payload.start_time,
            payload.end_time,
        )
    except MediaTrimNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaTrimConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (MediaTrimUnsupportedError, MediaTrimError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        db.rollback()
        logger.exception("Lossless media trim failed media_id=%s", item_id)
        raise HTTPException(status_code=500, detail="Lossless trim failed") from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Unexpected lossless media trim failure media_id=%s", item_id)
        raise HTTPException(status_code=500, detail="Lossless trim failed") from exc
    return {"status": "ok", "summary": summary}


def _karaoke_availability(media_item: MediaItem) -> tuple[bool, str | None, str | None]:
    if media_item.vocals_path and media_item.vocals_path.strip():
        return False, "already_multi_track", None
    health = runtime_settings_service.get_demucs_health()
    if not health.healthy:
        return False, "demucs_offline", health.detail
    return True, None, None


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str | None = Form(None),
    add_to_queue: bool = Form(True),
    is_karaoke: bool = Form(False),
    lyrics_text: str | None = Form(None),
    lyrics_format: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a new media file and create a library entry."""
    ext = Path(file.filename).suffix.lower()
    if ext not in _UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Supported uploads are .mp3, .mp4, .webm, .mkv, .mov, .avi, and .m4v",
        )

    normalized_title = queue_service._normalize_required_metadata(title)
    normalized_artist = queue_service._normalize_optional_metadata(artist)

    stem = build_media_stem(normalized_title, normalized_artist)
    final_stem = stem
    counter = 1
    while (settings.media_path / f"{final_stem}{ext}").exists():
        final_stem = f"{stem}_{counter}"
        counter += 1

    filename = f"{final_stem}{ext}"
    target_path = settings.media_path / filename
    queued_item = None
    karaoke_requested = bool(is_karaoke)
    karaoke_started = False
    karaoke_task_id = None
    karaoke_warning = None
    karaoke_warning_detail = None

    try:
        settings.media_path.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        media_item = MediaItem(
            title=normalized_title,
            artist=normalized_artist,
            file_stem=final_stem,
            media_path=queue_service.build_media_url(target_path),
            missing=False,
        )
        db.add(media_item)
        db.flush()
        media_thumbnail_service.ensure_thumbnail_for_media_file(target_path)
        if lyrics_text:
            if lyrics_format not in (None, "lrc", "txt"):
                raise HTTPException(status_code=400, detail="lyrics_format must be 'lrc' or 'txt'")
            queue_service.store_lyrics_sidecar(
                media_item,
                lyrics_text,
                lyrics_format=lyrics_format,
                storage="media",
            )

        karaoke_available = False
        if karaoke_requested:
            karaoke_available, karaoke_warning, karaoke_warning_detail = _karaoke_availability(
                media_item
            )

        if add_to_queue:
            queued_item = queue_service.add_to_queue(
                db,
                QueueItemCreate(
                    media_item_id=media_item.id,
                    title=media_item.title,
                    artist=media_item.artist,
                    is_karaoke=karaoke_requested and karaoke_available,
                ),
            )
            await manager.broadcast_queue_item_added(queued_item.model_dump(mode="json"))
        else:
            db.commit()
        db.refresh(media_item)

        try:
            if queued_item is not None:
                task = processing_task_service.get_or_create_queue_task(db, queued_item.id)
                task_execution_coordinator.start(task.id)
                karaoke_task_id = task.id if karaoke_requested and karaoke_available else None
                karaoke_started = bool(karaoke_task_id)
            elif karaoke_requested and karaoke_available:
                task = processing_task_service.get_or_create_media_task(db, media_item.id)
                task_execution_coordinator.start(task.id)
                karaoke_task_id = task.id
                karaoke_started = True
        except Exception as exc:
            logger.exception("Failed to start upload processing media_id=%s", media_item.id)
            if karaoke_requested:
                karaoke_warning = "task_start_failed"
                karaoke_warning_detail = str(exc)
    except HTTPException:
        db.rollback()
        if target_path.exists():
            target_path.unlink()
        media_thumbnail_service.remove_thumbnail_for_media_file(target_path)
        raise
    except Exception as exc:
        db.rollback()
        if target_path.exists():
            target_path.unlink()
        media_thumbnail_service.remove_thumbnail_for_media_file(target_path)
        logger.exception("Failed to upload media file: %s", filename)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(exc)}")

    logger.info(
        "Media uploaded: id=%s title=%s artist=%s add_to_queue=%s",
        media_item.id,
        media_item.title,
        media_item.artist,
        add_to_queue,
    )

    return {
        "status": "ok",
        "media_id": media_item.id,
        "filename": filename,
        "queued": bool(add_to_queue),
        "queue_item_id": queued_item.id if queued_item else None,
        "lyrics_path": media_item.lyrics_path,
        "karaoke_requested": karaoke_requested,
        "karaoke_started": karaoke_started,
        "karaoke_task_id": karaoke_task_id,
        "karaoke_warning": karaoke_warning,
        "karaoke_warning_detail": karaoke_warning_detail,
    }


@router.post("/{item_id}/karaoke")
def process_media_item_karaoke(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Create or reuse a durable karaoke task for an existing media item."""
    media_item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
    if media_item is None:
        raise HTTPException(status_code=404, detail="Media item not found")
    media_file = queue_service._media_url_to_file(media_item.media_path)
    if media_item.missing or media_file is None or not media_file.exists():
        raise HTTPException(status_code=409, detail="Media item file is missing")
    karaoke_available, warning, detail = _karaoke_availability(media_item)
    if not karaoke_available:
        if warning == "already_multi_track":
            raise HTTPException(status_code=409, detail="Media item is already multi-track capable")
        raise HTTPException(
            status_code=409,
            detail=f"Demucs unavailable: {detail or 'health check failed'}",
        )

    task = processing_task_service.get_or_create_media_task(db, item_id)
    task_execution_coordinator.start(task.id)
    return {"status": "processing", "media_id": item_id, "task_id": task.id}


@router.post("/scan")
def scan_media_library(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Run an on-demand filesystem sync for media library rows."""
    summary = media_library_sync_service.scan_library(db)
    return {"status": "ok", "summary": summary}


@router.post("/{item_id}/scan")
def scan_media_item(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Refresh sidecar and missing-state data for one media item."""
    try:
        summary = media_library_sync_service.scan_media_item(db, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "summary": summary}


@router.delete("/{item_id}")
def delete_media_item(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
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
def rename_media_item(
    item_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
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

    lyrics_text = payload.get("lyrics_text")
    if lyrics_text is not None and not isinstance(lyrics_text, str):
        raise HTTPException(status_code=400, detail="lyrics_text must be a string or null")
    lyrics_format = payload.get("lyrics_format")
    if lyrics_format not in (None, "lrc", "txt"):
        raise HTTPException(status_code=400, detail="lyrics_format must be 'lrc' or 'txt'")
    is_karaoke = payload.get("is_karaoke", False)
    if not isinstance(is_karaoke, bool):
        raise HTTPException(status_code=400, detail="is_karaoke must be a boolean")

    karaoke_started = False
    karaoke_task_id = None
    karaoke_warning = None
    karaoke_warning_detail = None

    try:
        summary = media_library_maintenance_service.rename_media_item(
            db,
            item_id,
            title=title,
            artist=artist,
            rename_on_disk=rename_on_disk,
        )
        if lyrics_text:
            media_item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
            if media_item is None:
                raise MediaItemNotFoundError(f"Media item not found: {item_id}")
            queue_service.store_lyrics_sidecar(
                media_item,
                lyrics_text,
                lyrics_format=lyrics_format,
                storage="media",
            )
            db.commit()
            summary["lyrics_path"] = media_item.lyrics_path

        media_item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
        if media_item is None:
            raise MediaItemNotFoundError(f"Media item not found: {item_id}")
        if is_karaoke:
            karaoke_available, karaoke_warning, karaoke_warning_detail = _karaoke_availability(
                media_item
            )
            if karaoke_available:
                try:
                    task = processing_task_service.get_or_create_media_task(db, item_id)
                    task_execution_coordinator.start(task.id)
                    karaoke_started = True
                    karaoke_task_id = task.id
                except Exception as exc:
                    logger.exception("Failed to start media karaoke task media_id=%s", item_id)
                    karaoke_warning = "task_start_failed"
                    karaoke_warning_detail = str(exc)
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaItemRenameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Failed to rename media item media_id=%s", item_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "ok",
        "summary": summary,
        "karaoke_requested": is_karaoke,
        "karaoke_started": karaoke_started,
        "karaoke_task_id": karaoke_task_id,
        "karaoke_warning": karaoke_warning,
        "karaoke_warning_detail": karaoke_warning_detail,
    }
