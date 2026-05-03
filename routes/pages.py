"""HTML page routes."""
from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from services.queue_service import QueueService
from services.media_library_service import MediaLibraryService
from services.runtime_settings_service import RuntimeSettingsService
from config import settings

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")
queue_service = QueueService()
media_library_service = MediaLibraryService()
runtime_settings_service = RuntimeSettingsService()


def app_url(path: str | None) -> str:
    """Prefix app-local absolute URLs with the configured deployment base path."""
    if not path:
        return settings.karaoke_base_path or ""
    if path.startswith(("http://", "https://", "ws://", "wss://", "//")):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    base_path = settings.karaoke_base_path
    if base_path and (path == base_path or path.startswith(f"{base_path}/")):
        return path
    return f"{base_path}{path}"


def is_active_path(request: Request, path: str) -> bool:
    """Return whether the current request is on an app-local path."""
    current_path = request.url.path
    target_path = app_url(path)
    return current_path == target_path or current_path.startswith(f"{target_path}/")


templates.env.globals["app_url"] = app_url
templates.env.globals["is_active_path"] = is_active_path
templates.env.filters["public_url"] = app_url


@router.get("/")
async def home(request: Request):
    """Home page redirects to login if no singer identified, else to queue."""
    if not request.cookies.get("karaoke_singer") and not request.cookies.get("karaoke_admin"):
        return RedirectResponse(url=app_url("/login"), status_code=302)
    return RedirectResponse(url=app_url("/queue"), status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login and identification page."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_handler(
    request: Request,
    response: Response,
    type: str = Form(...),
    username: str = Form(...),
    password: str = Form(None),
):
    """Handle login and identification."""
    if type == "admin":
        # Simple admin check for now, can be improved later
        # For prototype, we'll just accept any password or a simple one if provided in settings
        # Let's just set an admin cookie for now as requested for frontend implementation
        response = RedirectResponse(url=app_url("/queue"), status_code=302)
        response.set_cookie(key="karaoke_admin", value="true", path="/")
        return response
    else:
        # Guest identification
        response = RedirectResponse(url=app_url("/queue"), status_code=302)
        response.set_cookie(key="karaoke_singer", value=username, path="/")
        return response


@router.get("/logout")
async def logout(request: Request):
    """Log out and clear cookies."""
    response = RedirectResponse(url=app_url("/login"), status_code=302)
    response.delete_cookie(key="karaoke_singer", path="/")
    response.delete_cookie(key="karaoke_admin", path="/")
    return response


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
async def media_management_page(request: Request, db: Session = Depends(get_db)):
    """Media management page backed by persisted media library rows."""
    media_items = media_library_service.list_media_items(db)
    media_stats = media_library_service.get_media_stats(db)
    return templates.TemplateResponse(
        "media_management.html",
        {
            "request": request,
            "media_items": media_items,
            "media_stats": media_stats,
        },
    )


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Media upload page for adding new tracks."""
    return templates.TemplateResponse("upload.html", {"request": request})


@router.get("/access-restricted", response_class=HTMLResponse)
async def access_restricted_page(request: Request):
    """Static access gate page for reverse proxy network checks."""
    return templates.TemplateResponse(
        "access_restricted.html",
        {"request": request},
    )
