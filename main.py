"""Main FastAPI application"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from database import init_db
from config import settings

# Must be set before logging configuration is imported/executed.
if __name__ == "__main__":
    os.environ["KARAOKE_RELOAD_ACTIVE"] = "1"

from logging_config import configure_logging
from routes import media_files, pages, queue, search, settings as settings_routes
import logging

configure_logging()
logger = logging.getLogger(__name__)


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

    yield
    # Shutdown (cleanup if needed)
    logger.info("Shutting down karaoke application")


app = FastAPI(
    title="Karaoke App",
    description="Lightweight AI-powered karaoke application",
    version="0.1.0",
    lifespan=lifespan,
)

# Ensure filesystem-backed media directories exist before mounting.
settings.ensure_paths()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(media_files.router)
app.include_router(pages.router)
app.include_router(queue.router)
app.include_router(search.router)
app.include_router(settings_routes.router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    log_dir = Path(settings.log_dir)
    if log_dir.is_absolute():
        try:
            log_dir = log_dir.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            log_dir = Path("logs")

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_excludes=[
            str(log_dir),
            f"{log_dir}/*",
            f"{log_dir}/**/*",
            "logs/*",
            "*.log",
            "*.log.*",
        ],
    )
