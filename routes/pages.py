"""HTML page routes."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from services.queue_service import QueueService
from services.runtime_settings_service import RuntimeSettingsService

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")
queue_service = QueueService()
runtime_settings_service = RuntimeSettingsService()

MEDIA_PLACEHOLDER_ITEMS = [
    {
        "id": "m-starboy",
        "title": "Starboy",
        "artist": "The Weeknd ft. Daft Punk",
        "status": "synced",
        "thumbnail": "https://i.ytimg.com/vi/34Na4j8AVgA/hqdefault.jpg",
        "has_multi_track": True,
        "has_lyrics": True,
    },
    {
        "id": "m-levitating",
        "title": "Levitating",
        "artist": "Dua Lipa",
        "status": "new",
        "thumbnail": "https://i.ytimg.com/vi/TUVcZfQe-Kw/hqdefault.jpg",
        "has_multi_track": True,
        "has_lyrics": True,
    },
    {
        "id": "m-bohemian",
        "title": "Bohemian Rhapsody",
        "artist": "Queen",
        "status": "missing",
        "thumbnail": None,
        "has_multi_track": False,
        "has_lyrics": True,
    },
]


@router.get("/")
async def home(request: Request):
    """Home page redirects to queue."""
    return RedirectResponse(url="/queue", status_code=302)


@router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request, db: Session = Depends(get_db)):
    """Mobile queue page."""
    queue_items = queue_service.get_queue(db)
    return templates.TemplateResponse(
        "queue.html", {"request": request, "queue": queue_items}
    )


@router.get("/stage", response_class=HTMLResponse)
async def stage_page(request: Request, db: Session = Depends(get_db)):
    """Presentation-first stage player page."""
    current_item = queue_service.get_current_or_promote_next(db)
    queue_items = queue_service.get_queue(db)
    runtime_settings = runtime_settings_service.get_settings()
    return templates.TemplateResponse(
        "stage.html",
        {
            "request": request,
            "current": current_item,
            "queue": queue_items,
            "stage_qr_url": runtime_settings.stage_qr_url,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page for runtime app configuration."""
    return templates.TemplateResponse("settings.html", {"request": request})


@router.get("/media", response_class=HTMLResponse)
async def media_management_page(request: Request):
    """Placeholder media management page for library browsing/actions."""
    media_items = MEDIA_PLACEHOLDER_ITEMS
    media_stats = {
        "total": len(media_items),
        "with_multi_track": sum(1 for item in media_items if item["has_multi_track"]),
        "with_lyrics": sum(1 for item in media_items if item["has_lyrics"]),
        "missing": sum(1 for item in media_items if item["status"] == "missing"),
    }
    return templates.TemplateResponse(
        "media_management.html",
        {
            "request": request,
            "media_items": media_items,
            "media_stats": media_stats,
        },
    )
