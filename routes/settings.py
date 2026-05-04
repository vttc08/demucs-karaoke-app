"""API routes for runtime settings."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db

from models import (
    DemucsHealthResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
    YtDlpUpdateResponse,
    YtDlpVersionResponse,
)
from services.auth_service import ADMIN_SESSION_COOKIE, AuthService
from services.runtime_settings_service import RuntimeSettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])
runtime_settings_service = RuntimeSettingsService()
auth_service = AuthService()


def require_admin_session(request: Request, db: Session = Depends(get_db)):
    """Require a valid admin session for settings management APIs."""
    admin = auth_service.get_admin_for_session(
        db, request.cookies.get(ADMIN_SESSION_COOKIE)
    )
    if admin is None:
        raise HTTPException(status_code=403, detail="Admin session required")
    return admin


@router.get("/", response_model=RuntimeSettingsResponse)
def get_runtime_settings(_admin=Depends(require_admin_session)):
    """Get currently active runtime settings."""
    return runtime_settings_service.get_settings()


@router.patch("/", response_model=RuntimeSettingsResponse)
def update_runtime_settings(
    payload: RuntimeSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_session),
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


@router.get("/ytdlp/version", response_model=YtDlpVersionResponse)
def get_ytdlp_version(_admin=Depends(require_admin_session)):
    """Get current yt-dlp version."""
    try:
        return runtime_settings_service.get_ytdlp_version()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/ytdlp/update", response_model=YtDlpUpdateResponse)
def update_ytdlp(_admin=Depends(require_admin_session)):
    """Run yt-dlp self-update."""
    try:
        return runtime_settings_service.update_ytdlp()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))
