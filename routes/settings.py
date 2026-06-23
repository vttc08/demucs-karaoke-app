"""API routes for runtime settings."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db

from models import (
    DemucsGarbageCollectionResponse,
    DemucsHealthResponse,
    ProxyInfoRequest,
    ProxyInfoResponse,
    StorageUsageResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
    WhisperXPreloadRequest,
    WhisperXPreloadResponse,
    YtDlpUpdateResponse,
    YtDlpVersionResponse,
)
from routes.auth import require_admin_user
from services.runtime_settings_service import RuntimeSettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])
runtime_settings_service = RuntimeSettingsService()


@router.get("/", response_model=RuntimeSettingsResponse)
def get_runtime_settings(_admin=Depends(require_admin_user)):
    """Get currently active runtime settings."""
    return runtime_settings_service.get_settings()


@router.patch("/", response_model=RuntimeSettingsResponse)
def update_runtime_settings(
    payload: RuntimeSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Update runtime settings and apply immediately in-process."""
    try:
        return runtime_settings_service.update_settings(payload, db)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/demucs-health", response_model=DemucsHealthResponse)
def get_demucs_health():
    """Get current Demucs service health for configured API URL."""
    return runtime_settings_service.get_demucs_health()


@router.get("/storage-usage", response_model=StorageUsageResponse)
def get_storage_usage(_admin=Depends(require_admin_user)):
    """Estimate local media, cache, and database storage usage."""
    try:
        return runtime_settings_service.get_storage_usage()
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/demucs/gc", response_model=DemucsGarbageCollectionResponse)
def trigger_demucs_gc(_admin=Depends(require_admin_user)):
    """Trigger remote Demucs garbage collection."""
    try:
        return runtime_settings_service.trigger_demucs_garbage_collection()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/proxy-info", response_model=ProxyInfoResponse)
def get_proxy_info(
    payload: ProxyInfoRequest | None = None,
    _admin=Depends(require_admin_user),
):
    """Resolve public proxy egress details through ipinfo."""
    try:
        proxy_url = payload.proxy_url if payload else None
        return runtime_settings_service.get_proxy_info(proxy_url)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/whisperx/preload", response_model=WhisperXPreloadResponse)
def preload_whisperx_models(
    payload: WhisperXPreloadRequest,
    _admin=Depends(require_admin_user),
):
    """Trigger remote WhisperX model preload/download."""
    try:
        return runtime_settings_service.preload_whisperx_models(
            payload.whisperx_preload_models
        )
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/ytdlp/version", response_model=YtDlpVersionResponse)
def get_ytdlp_version(_admin=Depends(require_admin_user)):
    """Get current yt-dlp version."""
    try:
        return runtime_settings_service.get_ytdlp_version()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/ytdlp/update", response_model=YtDlpUpdateResponse)
def update_ytdlp(_admin=Depends(require_admin_user)):
    """Run yt-dlp self-update."""
    try:
        return runtime_settings_service.update_ytdlp()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))
