"""API routes for runtime settings."""
from fastapi import APIRouter, HTTPException

from models import (
    DemucsHealthResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
    YtDlpUpdateResponse,
    YtDlpVersionResponse,
)
from services.runtime_settings_service import RuntimeSettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])
runtime_settings_service = RuntimeSettingsService()


@router.get("/", response_model=RuntimeSettingsResponse)
def get_runtime_settings():
    """Get currently active runtime settings."""
    return runtime_settings_service.get_settings()


@router.patch("/", response_model=RuntimeSettingsResponse)
def update_runtime_settings(payload: RuntimeSettingsUpdateRequest):
    """Update runtime settings and apply immediately in-process."""
    try:
        return runtime_settings_service.update_settings(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/demucs-health", response_model=DemucsHealthResponse)
def get_demucs_health():
    """Get current Demucs service health for configured API URL."""
    return runtime_settings_service.get_demucs_health()


@router.get("/ytdlp/version", response_model=YtDlpVersionResponse)
def get_ytdlp_version():
    """Get current yt-dlp version."""
    try:
        return runtime_settings_service.get_ytdlp_version()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/ytdlp/update", response_model=YtDlpUpdateResponse)
def update_ytdlp():
    """Run yt-dlp self-update."""
    try:
        return runtime_settings_service.update_ytdlp()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))
