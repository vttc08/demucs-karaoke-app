"""Routes for serving generated media and cache files from stable URL prefixes."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import settings

router = APIRouter(tags=["media"])


def _resolve_safe_path(base_dir: Path, relative_path: str) -> Path:
    candidate = (base_dir / relative_path).resolve()
    base_resolved = base_dir.resolve()
    if not str(candidate).startswith(str(base_resolved)):
        raise HTTPException(status_code=400, detail="Invalid media path")
    return candidate


@router.get("/media/{file_path:path}")
def serve_media_file(file_path: str):
    """Serve files from the configured media directory under /media/*."""
    target = _resolve_safe_path(settings.media_path, file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(path=target)


@router.get("/cache/{file_path:path}")
def serve_cache_file(file_path: str):
    """Serve files from the configured cache directory under /cache/*."""
    target = _resolve_safe_path(settings.cache_path, file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Cache file not found")
    return FileResponse(path=target)
