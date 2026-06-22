"""Main FastAPI application"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from database import SessionLocal, init_db
from config import settings

# Must be set before logging configuration is imported/executed.
if __name__ == "__main__":
    os.environ["KARAOKE_RELOAD_ACTIVE"] = "1"

import logging
from logging_config import configure_logging
from routes import (
    media_files,
    lyrics,
    lyrics_presets,
    media_library,
    pages,
    queue,
    qr as qr_routes,
    search,
    settings as settings_routes,
    tasks as task_routes,
    vocal_sync,
)
from services.media_library_sync_service import MediaLibrarySyncService
from services.processing_task_service import processing_task_service, task_execution_coordinator
from services.websocket_manager import manager as websocket_manager

configure_logging()
logger = logging.getLogger(__name__)
media_library_sync_service = MediaLibrarySyncService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting karaoke application")
    logger.info("Tool configuration loaded: ytdlp=%s ffmpeg=%s", settings.ytdlp_path, settings.ffmpeg_path)

    settings.ensure_paths()
    logger.info(
        "Storage paths ensured: media=%s cache=%s logs=%s",
        settings.media_path,
        settings.cache_path,
        settings.log_dir,
    )

    init_db()
    logger.info("Database initialized")

    db = SessionLocal()
    try:
        applied_fields = settings_routes.runtime_settings_service.load_persisted_settings(db)
    finally:
        db.close()

    if applied_fields:
        logger.info("Loaded persisted runtime settings: %s", ", ".join(applied_fields))
    else:
        logger.info("No persisted runtime settings found")

    await websocket_manager.set_stage_vocals_volume(
        settings.stage_vocals_volume_default,
        source="startup",
    )

    recovered_task_ids: list[int] = []
    db = SessionLocal()
    try:
        scan_summary = media_library_sync_service.scan_library(db)
        logger.info(
            "Startup media scan summary created=%s missing=%s restored=%s sidecars=%s scanned_files=%s",
            scan_summary["created"],
            scan_summary["marked_missing"],
            scan_summary["restored"],
            scan_summary["sidecars_updated"],
            scan_summary["scanned_files"],
        )
        recovered_task_ids = processing_task_service.recover_interrupted_tasks(db)
    finally:
        db.close()

    for task_id in recovered_task_ids:
        logger.info("Restarting interrupted processing task task_id=%s", task_id)
        task_execution_coordinator.start(task_id)

    yield
    # Shutdown (cleanup if needed)
    logger.info("Shutting down karaoke application")


def create_app() -> FastAPI:
    """Create the FastAPI app with an optional deployment path prefix."""
    created_app = FastAPI(
        title="Karaoke App",
        description="Lightweight AI-powered karaoke application",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Ensure filesystem-backed media directories exist before mounting.
    settings.ensure_paths()

    base_path = settings.karaoke_base_path

    # Mount static files and include all route groups under the same public prefix.
    created_app.mount(f"{base_path}/static", StaticFiles(directory="static"), name="static")

    created_app.include_router(media_files.router, prefix=base_path)
    created_app.include_router(media_library.router, prefix=base_path)
    created_app.include_router(pages.router, prefix=base_path)
    created_app.include_router(lyrics.router, prefix=base_path)
    created_app.include_router(lyrics_presets.router, prefix=base_path)
    created_app.include_router(queue.router, prefix=base_path)
    created_app.include_router(qr_routes.router, prefix=base_path)
    created_app.include_router(search.router, prefix=base_path)
    created_app.include_router(settings_routes.router, prefix=base_path)
    created_app.include_router(task_routes.router, prefix=base_path)
    created_app.include_router(vocal_sync.router, prefix=base_path)

    @created_app.get(f"{base_path}/health")
    def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    return created_app


app = create_app()


def build_uvicorn_run_kwargs() -> dict[str, object]:
    """Build the Uvicorn launch arguments used by the local dev entrypoint."""
    log_dir = Path(settings.log_dir)
    if log_dir.is_absolute():
        try:
            log_dir = log_dir.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            log_dir = Path("logs")

    return {
        "host": settings.host,
        "port": settings.port,
        "reload": True,
        "reload_excludes": [
            str(log_dir),
            f"{log_dir}/*",
            f"{log_dir}/**/*",
            "logs/*",
            "*.log",
            "*.log.*",
        ],
        # Long-lived SSE and websocket clients should not block Ctrl-C or reload forever.
        "timeout_graceful_shutdown": 3,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", **build_uvicorn_run_kwargs())
