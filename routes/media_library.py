"""API routes for media library maintenance operations."""

import json
import logging
import shutil
import subprocess
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import (
    MediaCdgTranscodeRequest,
    MediaItem,
    MediaTrimRequest,
    ProcessingTaskResponse,
    QueueItemCreate,
    normalize_line_processing_settings,
)
from routes.auth import require_admin_user
from services.media_library_maintenance_service import (
    MediaItemDeleteConflictError,
    MediaItemNotFoundError,
    MediaFileDeleteConflictError,
    MediaFileKindError,
    MediaFileNotFoundError,
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
_UPLOAD_EXTENSIONS = {".mp3", ".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".zip"}
_MEDIA_UPLOAD_EXTENSIONS = {".mp3", ".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v"}
_ZIP_THUMBNAIL_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
_ZIP_LYRICS_EXTENSIONS = (".json", ".lrc", ".srt", ".txt", ".cdg")
_ZIP_VOCALS_EXTENSIONS = (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm")
_MEDIA_FILE_KINDS = {"main", "vocals", "lyrics"}


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


@router.post("/{item_id}/transcode-cdg", response_model=ProcessingTaskResponse)
def transcode_cdg_media_item(
    item_id: int,
    payload: MediaCdgTranscodeRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Render a legacy CDG sidecar into a standalone MP4 video."""
    media_item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
    if media_item is None:
        raise HTTPException(status_code=404, detail="Media item not found")

    media_file = queue_service._media_url_to_file(media_item.media_path)
    if media_item.missing or media_file is None or not media_file.is_file():
        raise HTTPException(status_code=404, detail="Media item file is missing")

    lyrics_file = queue_service._media_url_to_file(media_item.lyrics_path)
    if lyrics_file is None or not lyrics_file.is_file() or lyrics_file.suffix.lower() != ".cdg":
        raise HTTPException(status_code=422, detail="CDG lyrics sidecar is required")

    try:
        media_trim_service._assert_no_conflicts(db, item_id)
        task = processing_task_service.get_or_create_media_cdg_transcode_task(
            db,
            item_id,
            overwrite_original=payload.overwrite_original,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=422, detail=message) from exc

    task_execution_coordinator.start(task.id)
    return processing_task_service.to_response(task)


def _karaoke_availability(media_item: MediaItem) -> tuple[bool, str | None, str | None]:
    if media_item.vocals_path and media_item.vocals_path.strip():
        return False, "already_multi_track", None
    health = runtime_settings_service.get_demucs_health()
    if not health.healthy:
        return False, "demucs_offline", health.detail
    return True, None, None


def _demucs_availability() -> tuple[bool, str | None, str | None]:
    health = runtime_settings_service.get_demucs_health()
    if not health.healthy:
        return False, "demucs_offline", health.detail
    return True, None, None


def _validate_alignment_request(
    *,
    align_lyrics: bool,
    lyrics_text: str | None,
    lyrics_format: str | None,
) -> None:
    if not align_lyrics:
        return
    if not (lyrics_text or "").strip():
        raise HTTPException(status_code=400, detail="lyrics_text is required for lyrics alignment")
    if lyrics_format == "json":
        raise HTTPException(status_code=400, detail="WhisperX alignment requires plain text or LRC lyrics")


def _normalize_whisperx_align_language_override(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="whisperx_align_language_override must be a string or null")
    normalized = " ".join(value.split()).strip().lower()
    return normalized if normalized not in {"", "auto", "default"} else None


def _normalize_line_processing_request(
    process_lyrics_lines: object,
    max_line_length: object,
    max_line_length_cjk: object,
) -> tuple[bool, int | None, int | None]:
    try:
        return normalize_line_processing_settings(
            process_lyrics_lines,
            max_line_length,
            max_line_length_cjk,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _is_zip_root_entry(filename: str) -> bool:
    normalized = filename.replace("\\", "/").strip()
    if not normalized or normalized.endswith("/"):
        return False
    if normalized.startswith("__MACOSX/") or normalized == "__MACOSX":
        return False
    return "/" not in normalized


def _zip_entry_is_main_media(filename: str) -> bool:
    path = Path(filename)
    suffix = path.suffix.lower()
    if suffix not in _MEDIA_UPLOAD_EXTENSIONS:
        return False
    lower_name = filename.lower()
    if ".vocals." in lower_name or path.stem.lower().endswith(".vocals"):
        return False
    return True


def _select_zip_entry(
    archive: zipfile.ZipFile,
    stem: str,
    suffixes: tuple[str, ...],
) -> zipfile.ZipInfo | None:
    for candidate_suffix in suffixes:
        candidate_name = f"{stem}{candidate_suffix}"
        for info in archive.infolist():
            if info.filename.lower() != candidate_name.lower():
                continue
            if _is_zip_root_entry(info.filename):
                return info
    return None


def _select_zip_vocals_entry(
    archive: zipfile.ZipFile,
    stem: str,
    suffixes: tuple[str, ...],
) -> zipfile.ZipInfo | None:
    for candidate_suffix in suffixes:
        candidate_name = f"{stem}.vocals{candidate_suffix}"
        for info in archive.infolist():
            if info.filename.lower() != candidate_name.lower():
                continue
            if _is_zip_root_entry(info.filename):
                return info
    return None


def _media_target_paths_for_zip(
    media_root: Path,
    target_stem: str,
    main_suffix: str,
    vocals_entry: zipfile.ZipInfo | None,
    lyrics_entry: zipfile.ZipInfo | None,
    thumbnail_entry: zipfile.ZipInfo | None,
) -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = [("main", media_root / f"{target_stem}{main_suffix}")]
    if vocals_entry is not None:
        paths.append(("vocals", media_root / f"{target_stem}.vocals{Path(vocals_entry.filename).suffix.lower()}"))
    if lyrics_entry is not None:
        paths.append(("lyrics", media_root / f"{target_stem}{Path(lyrics_entry.filename).suffix.lower()}"))
    if thumbnail_entry is not None:
        paths.append(("thumbnail", media_root / f"{target_stem}{Path(thumbnail_entry.filename).suffix.lower()}"))
    return paths


def _copy_zip_entry_to_path(archive: zipfile.ZipFile, entry: zipfile.ZipInfo, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(entry) as source, target_path.open("wb") as destination:
        shutil.copyfileobj(source, destination)


def _cleanup_paths(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    title: str = Form(...),
    artist: str | None = Form(None),
    add_to_queue: bool = Form(True),
    is_karaoke: bool = Form(False),
    lyrics_text: str | None = Form(None),
    lyrics_format: str | None = Form(None),
    align_lyrics: bool = Form(False),
    whisperx_align_language_override: str | None = Form(None),
    process_lyrics_lines: bool = Form(False),
    max_line_length: int | None = Form(None),
    max_line_length_cjk: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a new media file and create a library entry."""
    ext = Path(file.filename).suffix.lower()
    if ext not in _UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Supported uploads are .mp3, .mp4, .webm, .mkv, .mov, .avi, .m4v, and .zip",
        )

    normalized_title = queue_service._normalize_required_metadata(title)
    normalized_artist = queue_service._normalize_optional_metadata(artist)
    queued_item = None
    karaoke_requested = bool(is_karaoke)
    alignment_requested = bool(align_lyrics)
    karaoke_started = False
    karaoke_task_id = None
    karaoke_warning = None
    karaoke_warning_detail = None
    whisperx_override = _normalize_whisperx_align_language_override(
        whisperx_align_language_override
    )
    (
        line_processing_requested,
        normalized_max_line_length,
        normalized_max_line_length_cjk,
    ) = _normalize_line_processing_request(
        process_lyrics_lines,
        max_line_length,
        max_line_length_cjk,
    )

    if ext == ".zip":
        karaoke_requested = False
        alignment_requested = False
        lyrics_text = None
        lyrics_format = None
        whisperx_override = None
        line_processing_requested = False
        normalized_max_line_length = None
        normalized_max_line_length_cjk = None
    elif alignment_requested:
        karaoke_requested = True

    try:
        if ext == ".zip":
            media_item, filename = _import_zip_media_bundle(
                db=db,
                upload_file=file,
                normalized_title=normalized_title,
                normalized_artist=normalized_artist,
            )
            if add_to_queue:
                queued_item = queue_service.add_to_queue(
                    db,
                    QueueItemCreate(
                        media_item_id=media_item.id,
                        title=media_item.title,
                        artist=media_item.artist,
                        is_karaoke=False,
                        align_lyrics=False,
                        process_lyrics_lines=False,
                    ),
                )
                await manager.broadcast_queue_item_added(queued_item.model_dump(mode="json"))
            else:
                db.commit()
            db.refresh(media_item)
        else:
            stem = build_media_stem(normalized_title, normalized_artist)
            final_stem = stem
            counter = 1
            while (settings.media_path / f"{final_stem}{ext}").exists():
                final_stem = f"{stem}_{counter}"
                counter += 1

            filename = f"{final_stem}{ext}"
            target_path = settings.media_path / filename

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

            lyrics_format = (lyrics_format or "").strip().lower() or None
            if lyrics_format not in (None, "lrc", "txt", "json"):
                raise HTTPException(status_code=400, detail="lyrics_format must be 'lrc', 'txt', or 'json'")
            _validate_alignment_request(
                align_lyrics=alignment_requested,
                lyrics_text=lyrics_text,
                lyrics_format=lyrics_format,
            )
            if lyrics_text:
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
                if not karaoke_available:
                    alignment_requested = False

            if add_to_queue:
                queued_item = queue_service.add_to_queue(
                    db,
                    QueueItemCreate(
                        media_item_id=media_item.id,
                        title=media_item.title,
                        artist=media_item.artist,
                        is_karaoke=karaoke_requested and karaoke_available,
                        align_lyrics=alignment_requested and karaoke_available,
                        whisperx_align_language_override=(
                            whisperx_override if alignment_requested and karaoke_available else None
                        ),
                        process_lyrics_lines=(
                            line_processing_requested if alignment_requested and karaoke_available else False
                        ),
                        max_line_length=(
                            normalized_max_line_length
                            if alignment_requested and karaoke_available
                            else None
                        ),
                        max_line_length_cjk=(
                            normalized_max_line_length_cjk
                            if alignment_requested and karaoke_available
                            else None
                        ),
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
                    task = (
                        processing_task_service.get_or_create_media_karaoke_align_task(
                            db,
                            media_item.id,
                            whisperx_align_language_override=whisperx_override,
                            process_lyrics_lines=line_processing_requested if alignment_requested else False,
                            max_line_length=(
                                normalized_max_line_length if alignment_requested else None
                            ),
                            max_line_length_cjk=(
                                normalized_max_line_length_cjk if alignment_requested else None
                            ),
                        )
                        if alignment_requested
                        else processing_task_service.get_or_create_media_task(
                            db,
                            media_item.id,
                            process_lyrics_lines=False,
                            max_line_length=None,
                            max_line_length_cjk=None,
                        )
                    )
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
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to upload media file: %s", file.filename)
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


def _import_zip_media_bundle(
    *,
    db: Session,
    upload_file: UploadFile,
    normalized_title: str,
    normalized_artist: str | None,
) -> tuple[MediaItem, str]:
    """Import a ZIP bundle containing one main media file and optional sidecars."""
    try:
        upload_file.file.seek(0)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(upload_file.file) as archive:
            root_entries = [
                info
                for info in archive.infolist()
                if not info.is_dir() and _is_zip_root_entry(info.filename)
            ]
            main_entries = [info for info in root_entries if _zip_entry_is_main_media(info.filename)]
            if not main_entries:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP imports must include one main audio or video file",
                )
            if len(main_entries) != 1:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP imports must include exactly one main audio or video file",
                )

            main_entry = main_entries[0]
            source_stem = Path(main_entry.filename).stem
            main_suffix = Path(main_entry.filename).suffix.lower()
            vocals_entry = _select_zip_vocals_entry(archive, source_stem, _ZIP_VOCALS_EXTENSIONS)
            lyrics_entry = _select_zip_entry(archive, source_stem, _ZIP_LYRICS_EXTENSIONS)
            thumbnail_entry = _select_zip_entry(archive, source_stem, _ZIP_THUMBNAIL_EXTENSIONS)

            settings.media_path.mkdir(parents=True, exist_ok=True)
            target_stem = source_stem
            counter = 1
            main_path = settings.media_path / f"{target_stem}{main_suffix}"
            while True:
                candidate_paths = _media_target_paths_for_zip(
                    settings.media_path,
                    target_stem,
                    main_suffix,
                    vocals_entry,
                    lyrics_entry,
                    thumbnail_entry,
                )
                if all(not path.exists() for _, path in candidate_paths):
                    break
                target_stem = f"{source_stem}_{counter}"
                counter += 1

            written_paths: list[Path] = []
            try:
                main_path = settings.media_path / f"{target_stem}{main_suffix}"
                import_plan: list[tuple[zipfile.ZipInfo, Path]] = [
                    (main_entry, main_path)
                ]
                if vocals_entry is not None:
                    import_plan.append(
                        (
                            vocals_entry,
                            settings.media_path / f"{target_stem}.vocals{Path(vocals_entry.filename).suffix.lower()}",
                        )
                    )
                if lyrics_entry is not None:
                    import_plan.append(
                        (
                            lyrics_entry,
                            settings.media_path / f"{target_stem}{Path(lyrics_entry.filename).suffix.lower()}",
                        )
                    )
                if thumbnail_entry is not None:
                    import_plan.append(
                        (
                            thumbnail_entry,
                            settings.media_path / f"{target_stem}{Path(thumbnail_entry.filename).suffix.lower()}",
                        )
                    )

                for entry, target_path in import_plan:
                    _copy_zip_entry_to_path(archive, entry, target_path)
                    written_paths.append(target_path)

                main_path = settings.media_path / f"{target_stem}{main_suffix}"
                media_item = MediaItem(
                    title=normalized_title,
                    artist=normalized_artist,
                    file_stem=target_stem,
                    media_path=queue_service.build_media_url(main_path),
                    missing=False,
                )
                if vocals_entry is not None:
                    media_item.vocals_path = queue_service.build_media_url(
                        settings.media_path / f"{target_stem}.vocals{Path(vocals_entry.filename).suffix.lower()}"
                    )
                if lyrics_entry is not None:
                    media_item.lyrics_path = queue_service.build_media_url(
                        settings.media_path / f"{target_stem}{Path(lyrics_entry.filename).suffix.lower()}"
                    )

                db.add(media_item)
                db.flush()
                media_thumbnail_service.ensure_thumbnail_for_media_file(main_path)
                db.commit()
                db.refresh(media_item)
                return media_item, main_path.name
            except Exception:
                media_thumbnail_service.remove_thumbnail_for_media_file(main_path)
                media_thumbnail_service.remove_thumbnail_sidecars_for_media_file(main_path)
                _cleanup_paths(written_paths)
                raise
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Uploaded ZIP file is not a valid archive") from exc


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

    task = processing_task_service.get_or_create_media_task(
        db,
        item_id,
        process_lyrics_lines=False,
        max_line_length=None,
        max_line_length_cjk=None,
    )
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


@router.get("/{item_id}/files")
def get_media_files(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Return the media file manifest for the edit modal."""
    try:
        return media_library_maintenance_service.get_media_file_manifest(db, item_id)
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{item_id}/files/{kind}/download")
def download_media_file(
    item_id: int,
    kind: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Download one tracked media file as an attachment."""
    normalized_kind = kind.strip().lower()
    if normalized_kind not in _MEDIA_FILE_KINDS:
        raise HTTPException(status_code=400, detail=f"Unsupported media file kind: {kind}")

    try:
        media_item, file_path, _entry = media_library_maintenance_service.get_media_file(
            db,
            item_id,
            normalized_kind,
        )
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaFileKindError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MediaFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")

    return FileResponse(path=file_path, filename=file_path.name)


@router.delete("/{item_id}/files/{kind}")
def delete_media_file(
    item_id: int,
    kind: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Delete one tracked sidecar file and clear the matching DB field."""
    normalized_kind = kind.strip().lower()
    if normalized_kind not in _MEDIA_FILE_KINDS:
        raise HTTPException(status_code=400, detail=f"Unsupported media file kind: {kind}")

    try:
        summary = media_library_maintenance_service.delete_media_file(
            db,
            item_id,
            normalized_kind,
        )
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaFileDeleteConflictError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MediaFileKindError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MediaFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Failed to delete media sidecar media_id=%s kind=%s", item_id, normalized_kind)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", "summary": summary}


@router.get("/{item_id}/download")
def download_media_package(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Download the current media item and available sidecars as a ZIP archive."""
    try:
        archive_bytes, archive_name = media_library_maintenance_service.build_media_zip(db, item_id)
    except MediaItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaFileKindError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    headers = {
        "Content-Disposition": f'attachment; filename="{archive_name}"',
    }
    return Response(content=archive_bytes, media_type="application/zip", headers=headers)


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
    lyrics_format = (lyrics_format or "").strip().lower() or None
    if lyrics_format not in (None, "lrc", "txt", "json"):
        raise HTTPException(status_code=400, detail="lyrics_format must be 'lrc', 'txt', or 'json'")
    is_karaoke = payload.get("is_karaoke", False)
    if not isinstance(is_karaoke, bool):
        raise HTTPException(status_code=400, detail="is_karaoke must be a boolean")
    align_lyrics = payload.get("align_lyrics", False)
    if not isinstance(align_lyrics, bool):
        raise HTTPException(status_code=400, detail="align_lyrics must be a boolean")
    whisperx_override = _normalize_whisperx_align_language_override(
        payload.get("whisperx_align_language_override")
    )
    process_lyrics_lines = payload.get("process_lyrics_lines", False)
    if not isinstance(process_lyrics_lines, bool):
        raise HTTPException(status_code=400, detail="process_lyrics_lines must be a boolean")
    max_line_length = payload.get("max_line_length")
    if max_line_length is not None and not isinstance(max_line_length, int):
        raise HTTPException(status_code=400, detail="max_line_length must be an integer or null")
    max_line_length_cjk = payload.get("max_line_length_cjk")
    if max_line_length_cjk is not None and not isinstance(max_line_length_cjk, int):
        raise HTTPException(status_code=400, detail="max_line_length_cjk must be an integer or null")
    (
        line_processing_requested,
        normalized_max_line_length,
        normalized_max_line_length_cjk,
    ) = _normalize_line_processing_request(
        process_lyrics_lines,
        max_line_length,
        max_line_length_cjk,
    )
    _validate_alignment_request(
        align_lyrics=align_lyrics,
        lyrics_text=lyrics_text,
        lyrics_format=lyrics_format,
    )

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
            if lyrics_format is None and media_item.lyrics_path:
                existing_suffix = Path(media_item.lyrics_path).suffix.lower().lstrip(".") or None
                if existing_suffix in {"lrc", "txt", "json"}:
                    lyrics_format = existing_suffix
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
        if is_karaoke or align_lyrics:
            if align_lyrics and media_item.vocals_path and media_item.vocals_path.strip():
                karaoke_available, karaoke_warning, karaoke_warning_detail = _demucs_availability()
            else:
                karaoke_available, karaoke_warning, karaoke_warning_detail = _karaoke_availability(
                    media_item
                )
            if karaoke_available:
                try:
                    if align_lyrics and media_item.vocals_path and media_item.vocals_path.strip():
                        task = processing_task_service.get_or_create_media_lyrics_align_task(
                            db,
                            item_id,
                            whisperx_align_language_override=whisperx_override,
                            process_lyrics_lines=line_processing_requested,
                            max_line_length=normalized_max_line_length,
                            max_line_length_cjk=normalized_max_line_length_cjk,
                        )
                    elif align_lyrics:
                        task = processing_task_service.get_or_create_media_karaoke_align_task(
                            db,
                            item_id,
                            whisperx_align_language_override=whisperx_override,
                            process_lyrics_lines=line_processing_requested,
                            max_line_length=normalized_max_line_length,
                            max_line_length_cjk=normalized_max_line_length_cjk,
                        )
                    else:
                        task = processing_task_service.get_or_create_media_task(
                            db,
                            item_id,
                            process_lyrics_lines=False,
                            max_line_length=None,
                            max_line_length_cjk=None,
                        )
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
