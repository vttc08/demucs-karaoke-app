"""HTML page routes."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from services.queue_service import QueueService

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")
queue_service = QueueService()


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


@router.get("/playback", response_class=HTMLResponse)
async def playback_page(request: Request, db: Session = Depends(get_db)):
    """TV playback page."""
    current_item = queue_service.get_current_or_promote_next(db)
    queue_items = queue_service.get_queue(db)
    return templates.TemplateResponse(
        "playback.html",
        {"request": request, "current": current_item, "queue": queue_items},
    )


@router.get("/stage", response_class=HTMLResponse)
async def stage_page(request: Request, db: Session = Depends(get_db)):
    """Presentation-first stage player page."""
    current_item = queue_service.get_current_or_promote_next(db)
    queue_items = queue_service.get_queue(db)
    return templates.TemplateResponse(
        "stage.html",
        {"request": request, "current": current_item, "queue": queue_items},
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page for runtime app configuration."""
    return templates.TemplateResponse("settings.html", {"request": request})
