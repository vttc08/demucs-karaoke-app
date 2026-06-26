"""HTML page routes."""
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from sqlalchemy.orm import Session
from database import get_db
from models import MediaItem, QueueStatus
from routes.auth import get_admin_user
from services.queue_service import QueueService
from services.media_library_service import MediaLibraryService
from services.media_trim_service import MediaTrimService
from services.processing_task_service import processing_task_service
from services.runtime_settings_service import RuntimeSettingsService
from services.subtitle_workflow_service import (
    SubtitleWorkflowConflictError,
    SubtitleWorkflowNotFoundError,
    subtitle_workflow_service,
)
from services.stage_lobby_service import StageLobbyService
from services.auth_service import ADMIN_SESSION_COOKIE, SESSION_DAYS, AuthService
from services.i18n_service import (
    LOCALE_COOKIE,
    catalog_payload,
    normalize_locale,
    resolve_locale,
    supported_locale_options,
    translate,
)
from config import settings

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")
queue_service = QueueService()
media_library_service = MediaLibraryService()
runtime_settings_service = RuntimeSettingsService()
stage_lobby_service = StageLobbyService()
media_trim_service = MediaTrimService()
auth_service = AuthService()
_VIDEO_SUFFIXES = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v"}
_DOCS_ROOT = "/help"


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


def static_asset_url(path: str) -> str:
    """Build a static asset URL with an mtime cache-buster when the file exists."""
    url = app_url(path)
    normalized = path.strip()
    if not normalized.startswith("/static/"):
        return url

    relative_path = normalized.removeprefix("/static/")
    asset_path = Path(__file__).resolve().parent.parent / "static" / relative_path
    try:
        version = asset_path.stat().st_mtime_ns
    except OSError:
        return url

    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={version}"


def build_docs_url(locale: str | None = None, path: str | None = None) -> str:
    """Build a docs-site URL for the given locale and optional page path."""
    active_locale = normalize_locale(locale) or locale or "en"
    docs_locale = active_locale.split("-", 1)[0].lower()
    docs_root = f"{_DOCS_ROOT}/" if docs_locale == "en" else f"{_DOCS_ROOT}/{docs_locale}/"
    normalized_path = (path or "").strip("/")
    if normalized_path:
        return f"{docs_root}{normalized_path}/"
    return docs_root


@pass_context
def docs_url(context, path: str | None = None, locale: str | None = None) -> str:
    """Build a docs URL using the active request locale unless overridden."""
    request = context.get("request")
    active_locale = locale or resolve_locale(request)
    return app_url(build_docs_url(active_locale, path))


def is_active_path(request: Request, path: str) -> bool:
    """Return whether the current request is on an app-local path."""
    current_path = request.url.path
    target_path = app_url(path)
    return current_path == target_path or current_path.startswith(f"{target_path}/")


templates.env.globals["app_url"] = app_url
templates.env.globals["static_asset_url"] = static_asset_url
templates.env.globals["is_active_path"] = is_active_path
templates.env.globals["docs_url"] = docs_url
templates.env.filters["public_url"] = app_url


@pass_context
def t(context, key: str, **params) -> str:
    """Translate a frontend UI string in templates."""
    return translate(resolve_locale(context.get("request")), key, **params)


def current_locale(request: Request) -> str:
    """Return the active locale code for templates."""
    return resolve_locale(request)


def normalized_cookie_value(value: str | None, *, max_length: int = 80) -> str:
    """Normalize lightweight cookie metadata for template decisions."""
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split()).strip()
    return normalized[:max_length]


def safe_next_url(next_url: str | None) -> str:
    """Constrain language redirects to app-local paths."""
    if not next_url:
        return app_url("/queue")
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return app_url("/queue")
    path = parsed.path or "/queue"
    base_path = settings.karaoke_base_path
    if base_path:
        if not (path == base_path or path.startswith(f"{base_path}/")):
            return app_url("/queue")
    elif not path.startswith("/"):
        return app_url("/queue")
    suffix = f"?{parsed.query}" if parsed.query else ""
    return f"{path}{suffix}"


templates.env.globals["t"] = t
templates.env.globals["current_locale"] = current_locale
templates.env.globals["supported_locales"] = supported_locale_options
templates.env.globals["i18n_catalogs"] = catalog_payload


@router.post("/language")
async def set_language(
    request: Request,
    language: str = Form(...),
    next: str = Form("/queue"),
):
    """Persist the selected frontend language in a browser cookie."""
    locale = normalize_locale(language) or "en"
    response = RedirectResponse(url=safe_next_url(next), status_code=302)
    response.set_cookie(
        key=LOCALE_COOKIE,
        value=locale,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=365 * 24 * 60 * 60,
        path="/",
    )
    return response


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
                    "error": translate(resolve_locale(request), "login.invalid_admin"),
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
    is_admin = get_admin_user(request, db) is not None
    runtime_settings = runtime_settings_service.get_settings()
    guest_id = normalized_cookie_value(request.cookies.get("karaoke_guest_id"))
    queue_items = queue_service.get_queue(
        db,
        is_admin=is_admin,
        requester_id=guest_id or None,
    )
    movable_items = [item for item in queue_items if item.status != QueueStatus.PLAYING]
    movable_index_by_id = {item.id: index for index, item in enumerate(movable_items)}
    singer_name = normalized_cookie_value(
        request.cookies.get("karaoke_singer"),
        max_length=40,
    )
    return templates.TemplateResponse(
        "queue.html",
        {
            "request": request,
            "queue": queue_items,
            "movable_count": len(movable_items),
            "movable_index_by_id": movable_index_by_id,
            "singer_name": singer_name,
            "needs_singer_name": not singer_name,
            "is_admin": is_admin,
            "stage_vocals_volume_default": runtime_settings.stage_vocals_volume_default,
        },
    )


@router.get("/queue/lyrics", response_class=HTMLResponse)
async def queue_lyrics_page(request: Request, db: Session = Depends(get_db)):
    """Queue-side lyrics viewer page for the currently playing item."""
    current_item = queue_service.get_current_item(db)
    return templates.TemplateResponse(
        "queue_lyrics.html",
        {
            "request": request,
            "current": current_item,
        },
    )


@router.get("/stage", response_class=HTMLResponse)
async def stage_page(request: Request, db: Session = Depends(get_db)):
    """Presentation-first stage player page."""
    if get_admin_user(request, db) is None:
        return RedirectResponse(url=app_url("/login"), status_code=302)
    current_item = queue_service.get_current_or_promote_next(db)
    queue_items = queue_service.get_queue(db)
    runtime_settings = runtime_settings_service.get_settings()
    lobby_media_url = stage_lobby_service.resolve_lobby_media_url()
    return templates.TemplateResponse(
        "stage.html",
        {
            "request": request,
            "current": current_item,
            "queue": queue_items,
            "stage_qr_url": runtime_settings.stage_qr_url,
            "stage_lobby_media_url": lobby_media_url,
            "stage_vocals_volume_default": runtime_settings.stage_vocals_volume_default,
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
    is_admin = get_admin_user(request, db) is not None
    task_items = (
        processing_task_service.list_tasks(db, include_done=False, include_failed=True, limit=20)
        if is_admin
        else []
    )
    return templates.TemplateResponse(
        "media_management.html",
        {
            "request": request,
            "media_items": media_items,
            "media_stats": media_stats,
            "is_admin": is_admin,
            "task_items": task_items,
        },
    )


@router.get("/media-editor/{item_id}", response_class=HTMLResponse)
async def media_editor_page(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Admin-only lossless trim editor for one media item."""
    admin = auth_service.get_admin_for_session(
        db, request.cookies.get(ADMIN_SESSION_COOKIE)
    )
    if admin is None:
        return RedirectResponse(url=app_url("/login"), status_code=302)

    media_item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
    if media_item is None or media_item.missing:
        return RedirectResponse(url=app_url("/media"), status_code=302)
    media_file = queue_service._media_url_to_file(media_item.media_path)
    if media_file is None or not media_file.is_file():
        return RedirectResponse(url=app_url("/media"), status_code=302)

    media_suffix = Path(media_item.media_path).suffix.lower()
    is_video = media_suffix in _VIDEO_SUFFIXES
    return templates.TemplateResponse(
        "media_editor.html",
        {
            "request": request,
            "trim_info": {
                "media_id": media_item.id,
                "title": media_item.title,
                "artist": media_item.artist,
                "media_url": media_item.media_path,
                "has_video": is_video,
            },
        },
    )


@router.get("/media-vocals/{item_id}", response_class=HTMLResponse)
async def media_vocals_page(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Admin-only editor for adding synchronized guide vocals to one media item."""
    admin = auth_service.get_admin_for_session(
        db, request.cookies.get(ADMIN_SESSION_COOKIE)
    )
    if admin is None:
        return RedirectResponse(url=app_url("/login"), status_code=302)

    media_item = db.query(MediaItem).filter(MediaItem.id == item_id).first()
    if media_item is None or media_item.missing:
        return RedirectResponse(url=app_url("/media"), status_code=302)
    media_file = queue_service._media_url_to_file(media_item.media_path)
    if media_file is None or not media_file.is_file():
        return RedirectResponse(url=app_url("/media"), status_code=302)

    media_suffix = Path(media_item.media_path).suffix.lower()
    is_video = media_suffix in _VIDEO_SUFFIXES
    return templates.TemplateResponse(
        "media_vocals.html",
        {
            "request": request,
            "vocal_sync": {
                "media_id": media_item.id,
                "title": media_item.title,
                "artist": media_item.artist,
                "media_url": media_item.media_path,
                "has_video": is_video,
                "has_vocals": bool(media_item.vocals_path and media_item.vocals_path.strip()),
            },
        },
    )


@router.get("/media-subtitles/{item_id}", response_class=HTMLResponse)
async def media_subtitles_page(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Admin-only subtitle workflow editor for one media item."""
    admin = auth_service.get_admin_for_session(
        db, request.cookies.get(ADMIN_SESSION_COOKIE)
    )
    if admin is None:
        return RedirectResponse(url=app_url("/login"), status_code=302)
    locale = resolve_locale(request)

    try:
        media_item, media_file, lyrics_file = subtitle_workflow_service.get_editable_media(db, item_id)
    except (SubtitleWorkflowNotFoundError, SubtitleWorkflowConflictError) as exc:
        if isinstance(exc, SubtitleWorkflowConflictError):
            detail = translate(locale, "subtitle.not_available_detail")
        else:
            detail = translate(locale, "subtitle.not_found_detail")
        return templates.TemplateResponse(
            "media_subtitles.html",
            {
                "request": request,
                "subtitle_error": {
                    "title": translate(locale, "subtitle.not_available"),
                    "detail": detail,
                    "back_url": app_url("/media"),
                    "history_back": translate(locale, "subtitle.go_back_previous"),
                },
            },
            status_code=404,
        )

    media_suffix = Path(media_item.media_path).suffix.lower()
    is_video = media_suffix in _VIDEO_SUFFIXES
    docs_target = app_url(build_docs_url(locale))
    return templates.TemplateResponse(
        "media_subtitles.html",
        {
            "request": request,
            "subtitle_info": {
                "media_id": media_item.id,
                "title": media_item.title,
                "artist": media_item.artist,
                "media_url": media_item.media_path,
                "lyrics_url": media_item.lyrics_path,
                "has_video": is_video,
                "media_name": media_file.name,
                "lyrics_name": lyrics_file.name,
                "ass_export_url": app_url(f"/api/media/{media_item.id}/subtitles/ass"),
                "srt_export_url": app_url(f"/api/media/{media_item.id}/subtitles/srt"),
                "preview_url": app_url(f"/api/media/{media_item.id}/subtitles/preview"),
                "upload_url": app_url(f"/api/media/{media_item.id}/subtitles/upload"),
                "raw_upload_url": app_url(f"/api/media/{media_item.id}/subtitles/raw-upload"),
                "files_url": app_url(f"/api/media/{media_item.id}/files"),
                "package_url": app_url(f"/api/media/{media_item.id}/download"),
                "docs_url": docs_target,
            },
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
