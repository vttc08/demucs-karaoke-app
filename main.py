"""Main FastAPI application."""
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from database import init_db
from config import settings
from routes import queue, search, pages, settings as settings_routes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting karaoke application...")
    logger.info(f"yt-dlp path: {settings.ytdlp_path}")
    logger.info(f"ffmpeg path: {settings.ffmpeg_path}")
    
    settings.ensure_paths()
    logger.info(f"Media path: {settings.media_path}")
    logger.info(f"Cache path: {settings.cache_path}")
    
    init_db()
    logger.info("Database initialized")
    
    yield
    # Shutdown (cleanup if needed)
    logger.info("Shutting down karaoke application...")


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
app.mount(
    str(settings.media_path),
    StaticFiles(directory=str(settings.media_path)),
    name="media-files",
)
app.mount(
    str(settings.cache_path),
    StaticFiles(directory=str(settings.cache_path)),
    name="cache-files",
)

# Include routers
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

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
