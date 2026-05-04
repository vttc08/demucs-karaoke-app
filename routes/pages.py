"""HTML page routes."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from services.queue_service import QueueService
from services.media_library_service import MediaLibraryService
from services.runtime_settings_service import RuntimeSettingsService
from services.auth_service import ADMIN_SESSION_COOKIE, SESSION_DAYS, AuthService
from config import settings

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")
queue_service = QueueService()
media_library_service = MediaLibraryService()
runtime_settings_service = RuntimeSettingsService()
auth_service = AuthService()


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
    """Home page redirects to the queue without forcing guest identification."""
    return RedirectResponse(url=app_url("/queue"), status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Login and identification page."""
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "admin_configured": auth_service.count_admins(db) > 0,
            "error": None,
            "login_mode": "guest",
        },
    )


@router.post("/login")
async def login_handler(
    request: Request,
    type: str = Form(...),
    username: str = Form(...),
    password: str = Form(None),
    db: Session = Depends(get_db),
):
    """Handle login and identification."""
    if type == "admin":
        admin = auth_service.authenticate_admin(db, username, password)
        if admin is None:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "admin_configured": auth_service.count_admins(db) > 0,
                    "error": "Invalid admin username or password.",
                    "login_mode": "admin",
                },
                status_code=401,
            )

        token, _ = auth_service.create_admin_session(db, admin)
        response = RedirectResponse(url=app_url("/queue"), status_code=302)
        response.set_cookie(
            key=ADMIN_SESSION_COOKIE,
            value=token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=SESSION_DAYS * 24 * 60 * 60,
            path="/",
        )
        return response

    # Guest identification remains a lightweight display name for this sprint.
    response = RedirectResponse(url=app_url("/queue"), status_code=302)
    response.set_cookie(
        key="karaoke_singer",
        value=username.strip(),
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """Log out and clear cookies."""
    auth_service.delete_admin_session(db, request.cookies.get(ADMIN_SESSION_COOKIE))
    response = RedirectResponse(url=app_url("/login"), status_code=302)
    response.delete_cookie(key="karaoke_singer", path="/")
    response.delete_cookie(key=ADMIN_SESSION_COOKIE, path="/")
    return response


@router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request, db: Session = Depends(get_db)):
    """Mobile queue page."""
    queue_items = queue_service.get_queue(db)
    singer_name = (request.cookies.get("karaoke_singer") or "").strip()
    return templates.TemplateResponse(
        "queue.html",
        {
            "request": request,
            "queue": queue_items,
            "singer_name": singer_name,
            "needs_singer_name": not singer_name,
        },
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
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """Settings page for runtime app configuration."""
    admin = auth_service.get_admin_for_session(
        db, request.cookies.get(ADMIN_SESSION_COOKIE)
    )
    if admin is None:
        return RedirectResponse(url=app_url("/login"), status_code=302)
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
