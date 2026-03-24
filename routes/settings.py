"""API routes for runtime settings."""
from fastapi import APIRouter, HTTPException

from models import DemucsHealthResponse, RuntimeSettingsResponse, RuntimeSettingsUpdateRequest
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
