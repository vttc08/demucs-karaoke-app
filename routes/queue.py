"""API routes for queue management."""
import asyncio
import json
import logging
import math
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from config import settings
from database import get_db
from models import ProcessingTaskResponse, QueueItem, QueueItemCreate, QueueItemMoveRequest, QueueItemResponse, QueueStatus
from routes.auth import auth_service, get_admin_user, require_admin_user
from services.lyrics_service import LyricsService
from services.lyrics_preset_service import (
    LyricsPresetNotFoundError,
    lyrics_preset_service,
)
from services.processing_task_service import processing_task_service, task_execution_coordinator
from services.auth_service import ADMIN_SESSION_COOKIE
from services.queue_service import QueueService
from services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/queue", tags=["queue"])
queue_service = QueueService()
lyrics_service = LyricsService()


def _normalize_presence_value(value: str | None, *, max_length: int = 80) -> str | None:
    """Normalize cookie or websocket presence values."""
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _current_guest_id(request: Request) -> str | None:
    """Return the normalized persistent guest id for the current request."""
    return _normalize_presence_value(request.cookies.get("karaoke_guest_id"))


def _websocket_guest_id(websocket: WebSocket) -> str | None:
    """Return the normalized persistent guest id for a websocket connection."""
    return _normalize_presence_value(websocket.cookies.get("karaoke_guest_id"))


def _normalize_websocket_role(value: object) -> str | None:
    """Validate and normalize a websocket client role."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"queue", "stage", "lyrics_viewer"}:
        return normalized
    return None


def _normalize_stage_id(value: object) -> str | None:
    """Validate and normalize a stage display id from websocket payloads."""
    return _normalize_presence_value(value if isinstance(value, str) else None, max_length=120)


def _normalize_stage_name(value: object) -> str | None:
    """Validate and normalize a stage display name from websocket payloads."""
    return _normalize_presence_value(value if isinstance(value, str) else None, max_length=80)


def _default_stage_name(stage_id: str) -> str:
    """Return a fallback label for a stage display when the client sends none."""
    compact_id = "".join(character for character in stage_id if character.isalnum())
    suffix = (compact_id[-4:] or stage_id[-4:]).upper()
    return f"Stage {suffix}"


def _validated_queue_as_guest_id(item: QueueItemCreate) -> str | None:
    """Validate the delegated guest id for an admin queue-as request."""
    if item.queue_as_guest_id is None:
        return None
    guest_id = _normalize_presence_value(item.queue_as_guest_id)
    if guest_id is None:
        raise HTTPException(
            status_code=400,
            detail="queue_as_guest_id must be a non-empty guest id",
        )
    return guest_id


def _is_admin_websocket(websocket: WebSocket, db: Session) -> bool:
    """Return whether a websocket connection has a valid admin session."""
    return (
        auth_service.get_admin_for_session(
            db, websocket.cookies.get(ADMIN_SESSION_COOKIE)
        )
        is not None
    )


def _can_control_current_stage(
    db: Session,
    *,
    is_admin: bool,
    requester_id: str | None,
) -> bool:
    """Return whether the viewer may control the currently playing item."""
    if is_admin:
        return True
    current = (
        db.query(QueueItem)
        .filter(QueueItem.status == QueueStatus.PLAYING)
        .order_by(QueueItem.position.asc(), QueueItem.id.asc())
        .first()
    )
    if current is None:
        return False
    return queue_service.can_control_stage_item(
        current,
        requester_id=requester_id,
    )


async def _send_ws_error(websocket: WebSocket, detail: str) -> None:
    """Send a structured websocket error to one client."""
    await manager.send_personal_message(
        {
            "type": "error",
            "data": {"detail": detail},
            "timestamp": asyncio.get_event_loop().time(),
        },
        websocket,
    )


async def _resolve_target_stage_id(
    websocket: WebSocket,
    manager_instance,
    detail_prefix: str,
    payload: dict,
) -> str | None:
    """Resolve a target stage id, falling back to the only connected display."""
    target_stage_id = _normalize_stage_id(payload.get("target_stage_id"))
    if not target_stage_id:
        stages = manager_instance.get_stage_presence_snapshot()
        if len(stages) == 1:
            target_stage_id = stages[0]["stage_id"]
        else:
            await _send_ws_error(websocket, f"{detail_prefix} require a target stage")
            return None
    if not manager_instance.has_stage_display(target_stage_id):
        await _send_ws_error(websocket, "Target stage is not connected")
        return None
    return target_stage_id


@router.post("/", response_model=QueueItemResponse)
async def add_to_queue(
    item: QueueItemCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Add item to queue."""
    is_admin = get_admin_user(request, db) is not None
    requester_name = _normalize_presence_value(
        request.cookies.get("karaoke_singer"), max_length=40
    )
    queue_as_guest_id: str | None = None
    if item.queue_as_name is not None:
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="queue_as_name requires an admin session",
            )
        requester_name = _normalize_presence_value(item.queue_as_name, max_length=40)
        queue_as_guest_id = _validated_queue_as_guest_id(item)
    elif item.queue_as_guest_id is not None:
        raise HTTPException(
            status_code=403,
            detail="queue_as_guest_id requires an admin session",
        )

    try:
        response = queue_service.add_to_queue(
            db,
            item,
            requester_id=_normalize_presence_value(
                request.cookies.get("karaoke_guest_id")
            ),
            requester_session_id=_normalize_presence_value(
                request.cookies.get("karaoke_queue_tab_id")
            ),
            requester_name=requester_name,
            owner_guest_id=queue_as_guest_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Broadcast immediately after adding
    await manager.broadcast_queue_item_added(response.model_dump(mode="json"))
    return response


@router.get("/", response_model=List[QueueItemResponse])
def get_queue(request: Request, db: Session = Depends(get_db)):
    """Get all items in queue."""
    is_admin = get_admin_user(request, db) is not None
    return queue_service.get_queue(
        db,
        is_admin=is_admin,
        requester_id=_current_guest_id(request),
    )


@router.get("/presence")
def get_queue_presence():
    """Return the current in-memory queue presence roster."""
    return {"users": manager.get_queue_presence_snapshot()}


@router.get("/current", response_model=QueueItemResponse | None)
def get_current(db: Session = Depends(get_db)):
    """Get currently playing item."""
    return queue_service.get_current_item(db)


@router.get("/next", response_model=QueueItemResponse | None)
def get_next(db: Session = Depends(get_db)):
    """Get next item in queue."""
    return queue_service.get_next_item(db)


@router.get("/{item_id}/lyrics-cues")
def get_lyrics_cues(item_id: int, db: Session = Depends(get_db)):
    """Get normalized lyrics payload for a queue item."""
    item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    item_response = queue_service._to_response(item)
    lyrics_path = item_response.lyrics_path
    if not lyrics_path:
        raise HTTPException(status_code=404, detail="Lyrics not available for queue item")

    try:
        lyrics_payload = lyrics_service.load_lyrics_payload_from_media_url(lyrics_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid lyrics JSON: {exc}") from exc

    return {
        "item_id": item.id,
        "media_id": item.media_id,
        "lyrics_path": lyrics_path,
        "source_format": lyrics_payload["source_format"],
        "is_synced": lyrics_payload["is_synced"],
        "cues": lyrics_payload["cues"],
        "lines": lyrics_payload["lines"],
    }


@router.post("/skip", response_model=QueueItemResponse | None)
async def skip_current(request: Request, db: Session = Depends(get_db)):
    """Skip current item and promote next ready item to playing."""
    is_admin = get_admin_user(request, db) is not None
    if not _can_control_current_stage(
        db,
        is_admin=is_admin,
        requester_id=_current_guest_id(request),
    ):
        raise HTTPException(status_code=403, detail="Not allowed to control this stage item")

    current = queue_service.get_current_item(db)
    result = queue_service.skip_current_item(db)

    await manager.broadcast_current_item_changed(
        result.id if result else None,
        current.id if current else None,
    )

    return result


@router.post("/complete-current", response_model=QueueItemResponse | None)
async def complete_current(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Complete current item and promote next ready item to playing."""
    current = queue_service.get_current_item(db)
    result = queue_service.complete_current_item(db)

    await manager.broadcast_current_item_changed(
        result.id if result else None,
        current.id if current else None,
    )

    return result


@router.post("/skip-to/{item_id}", response_model=QueueItemResponse | None)
async def skip_to_item(
    item_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Skip to a specific item in the queue."""
    item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    
    if item.status != "ready":
        raise HTTPException(status_code=400, detail="Item is not ready for playback")
    
    current = queue_service.get_current_item(db)
    previous_id = current.id if current else None

    if previous_id is not None and previous_id != item_id:
        db.query(QueueItem).filter(QueueItem.id == previous_id).delete()

    db.query(QueueItem).filter(
        QueueItem.id != item_id, QueueItem.status == QueueStatus.PLAYING
    ).update({QueueItem.status: QueueStatus.READY}, synchronize_session=False)
    item.status = QueueStatus.PLAYING
    db.commit()
    db.refresh(item)

    await manager.broadcast_current_item_changed(item_id, previous_id)

    return queue_service._to_response(item)


@router.post("/{item_id}/move", response_model=QueueItemResponse)
async def move_item(
    item_id: int,
    payload: QueueItemMoveRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Move an active queue item up or down within the queue order."""
    try:
        response = queue_service.move_queue_item(db, item_id, payload.direction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await manager.broadcast_queue_item_updated(response.model_dump(mode="json"))
    return response


@router.delete("/{item_id}")
async def remove_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Remove an item from the queue."""
    item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    is_admin = get_admin_user(request, db) is not None
    if not queue_service.can_manage_queue_item(
        item,
        is_admin=is_admin,
        requester_id=_current_guest_id(request),
    ):
        raise HTTPException(status_code=403, detail="Not allowed to remove this queue item")

    if item.status == QueueStatus.PLAYING:
        raise HTTPException(status_code=400, detail="Cannot remove currently playing item")

    db.delete(item)
    db.commit()

    # Broadcast removal
    await manager.broadcast_queue_item_removed(item_id)

    return {"status": "removed", "item_id": item_id}


@router.post("/clear")
async def clear_queue(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_user),
):
    """Clear all items from the queue except currently playing."""
    # Remove all items except the currently playing one
    db.query(QueueItem).filter(QueueItem.status != "playing").delete()
    db.commit()
    
    # Broadcast clear
    await manager.broadcast_queue_cleared()
    
    return {"status": "cleared"}


@router.post("/{item_id}/process")
def process_item(
    item_id: int,
    db: Session = Depends(get_db),
):
    """Trigger processing of a queue item without blocking the request."""
    item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    task = processing_task_service.get_or_create_queue_task(db, item_id)
    task_execution_coordinator.start(task.id)
    return {"status": "processing", "item_id": item_id, "task_id": task.id}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    """WebSocket endpoint for real-time queue updates."""
    await manager.connect(websocket)
    
    try:
        # Send initial connection confirmation
        await manager.send_personal_message(
            {
                "type": "connected",
                "data": {
                    "connection_count": manager.get_connection_count(),
                    "stage_state": manager.get_stage_state(),
                },
                "timestamp": asyncio.get_event_loop().time()
            },
            websocket
        )
        
        # Heartbeat task
        async def send_heartbeat():
            """Send periodic heartbeat to keep connection alive."""
            interval_seconds = max(1.0, float(settings.ws_heartbeat_interval))
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    if await manager.is_connection_stale(
                        websocket,
                        heartbeat_interval_seconds=interval_seconds,
                    ):
                        logger.info("Closing stale websocket connection")
                        await websocket.close(code=1001, reason="heartbeat timeout")
                        break
                    await manager.mark_connection_ping(websocket)
                    await websocket.send_json({
                        "type": "ping",
                        "timestamp": asyncio.get_event_loop().time()
                    })
                except Exception:
                    break
        
        heartbeat_task = asyncio.create_task(send_heartbeat())
        
        # Listen for client messages
        while True:
            data = await websocket.receive_json()
            await manager.touch_connection(websocket)

            # Handle pong response
            if data.get("type") == "pong":
                await manager.mark_connection_pong(websocket)
                logger.debug("Received pong from client")
                continue

            if data.get("type") == "client_subscribe":
                payload = data.get("data")
                if not isinstance(payload, dict):
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": "Invalid client_subscribe payload"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue

                role = _normalize_websocket_role(payload.get("page"))
                if role is None:
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": "client_subscribe requires page=queue|stage|lyrics_viewer"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue
                await manager.set_connection_role(websocket, role)
                continue

            if data.get("type") == "stage_presence_hello":
                payload = data.get("data")
                if not isinstance(payload, dict):
                    await _send_ws_error(websocket, "Invalid stage_presence_hello payload")
                    continue
                stage_id = _normalize_stage_id(payload.get("stage_id"))
                stage_name = _normalize_stage_name(payload.get("stage_name")) or _default_stage_name(stage_id or "")
                if not stage_id:
                    await _send_ws_error(websocket, "stage_presence_hello requires stage_id")
                    continue
                await manager.register_stage_presence(
                    websocket,
                    stage_id=stage_id,
                    stage_name=stage_name,
                )
                continue

            if data.get("type") == "stage_presence_request":
                await manager.send_stage_presence_snapshot(websocket)
                continue

            if data.get("type") == "lyrics_settings_ack":
                payload = data.get("data")
                if not isinstance(payload, dict):
                    await _send_ws_error(websocket, "Invalid lyrics_settings_ack payload")
                    continue
                stage_id = _normalize_stage_id(payload.get("stage_id"))
                if not stage_id:
                    await _send_ws_error(websocket, "lyrics_settings_ack requires stage_id")
                    continue
                await manager.broadcast_lyrics_settings_ack(
                    {
                        "stage_id": stage_id,
                        "ok": bool(payload.get("ok")),
                        "preset_id": payload.get("preset_id") if isinstance(payload.get("preset_id"), int) else None,
                        "override": payload.get("override") if isinstance(payload.get("override"), bool) else None,
                        "size_vw": payload.get("size_vw") if isinstance(payload.get("size_vw"), (int, float)) else None,
                        "line_width_pct": payload.get("line_width_pct") if isinstance(payload.get("line_width_pct"), int) else None,
                        "background_media_enabled": payload.get("background_media_enabled") if isinstance(payload.get("background_media_enabled"), bool) else None,
                        "applied_settings": payload.get("applied_settings") if isinstance(payload.get("applied_settings"), dict) else None,
                        "error": _normalize_presence_value(payload.get("error"), max_length=160),
                    }
                )
                continue

            if data.get("type") in {"presence_hello", "presence_update"}:
                payload = data.get("data")
                if not isinstance(payload, dict):
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": "Invalid presence payload"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue

                if payload.get("page") != "queue":
                    continue

                guest_id = _normalize_presence_value(payload.get("guest_id"))
                display_name = _normalize_presence_value(
                    payload.get("display_name"), max_length=40
                )
                tab_id = _normalize_presence_value(payload.get("tab_id"))
                if not guest_id or not tab_id or not display_name:
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {
                                "detail": "presence messages require guest_id, display_name, and tab_id"
                            },
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue

                if data.get("type") == "presence_hello":
                    await manager.register_queue_presence(
                        websocket,
                        guest_id=guest_id,
                        display_name=display_name,
                        tab_id=tab_id,
                    )
                else:
                    await manager.update_queue_presence(
                        websocket,
                        guest_id=guest_id,
                        display_name=display_name,
                        tab_id=tab_id,
                    )
                continue

            if data.get("type") == "stage_command":
                payload = data.get("data")
                if not isinstance(payload, dict):
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": "Invalid stage_command payload"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue

                command = payload.get("command")
                source = payload.get("source", "unknown")
                if command not in {"play", "pause", "skip", "seek", "seek_relative", "resync", "set_vocals_enabled", "set_vocals_volume", "set_lyrics_enabled", "set_background_media_enabled", "apply_lyrics_settings"}:
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": f"Unsupported stage command: {command}"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue

                is_admin = _is_admin_websocket(websocket, db)
                if command == "apply_lyrics_settings":
                    if not is_admin:
                        await _send_ws_error(websocket, "Admin session required for lyrics settings")
                        continue
                    target_stage_id = await _resolve_target_stage_id(websocket, manager, "Lyrics settings", payload)
                    if not target_stage_id:
                        continue

                    lyrics_enabled = payload.get("lyrics_enabled")
                    if lyrics_enabled is not None and not isinstance(lyrics_enabled, bool):
                        await _send_ws_error(websocket, "lyrics_enabled must be boolean")
                        continue
                    background_media_enabled = payload.get("background_media_enabled")
                    if background_media_enabled is not None and not isinstance(background_media_enabled, bool):
                        await _send_ws_error(websocket, "background_media_enabled must be boolean")
                        continue

                    preset_id = payload.get("preset_id")
                    if preset_id is not None:
                        if not isinstance(preset_id, int) or preset_id <= 0:
                            await _send_ws_error(websocket, "preset_id must be a positive integer")
                            continue
                        try:
                            lyrics_preset_service.get_preset(db, preset_id)
                        except LyricsPresetNotFoundError:
                            await _send_ws_error(websocket, "Lyrics preset not found")
                            continue

                    raw_size = payload.get("size_vw")
                    size_vw = None
                    if raw_size is not None:
                        if not isinstance(raw_size, (int, float)) or not math.isfinite(float(raw_size)):
                            await _send_ws_error(websocket, "size_vw must be numeric")
                            continue
                        size_vw = float(raw_size)
                        if size_vw < 3.2 or size_vw > 8.8:
                            await _send_ws_error(websocket, "size_vw must be between 3.2 and 8.8")
                            continue

                    raw_width = payload.get("line_width_pct")
                    line_width_pct = None
                    if raw_width is not None:
                        if not isinstance(raw_width, (int, float)) or not math.isfinite(float(raw_width)):
                            await _send_ws_error(websocket, "line_width_pct must be numeric")
                            continue
                        line_width_pct = int(round(float(raw_width)))
                        if line_width_pct < 60 or line_width_pct > 100:
                            await _send_ws_error(websocket, "line_width_pct must be between 60 and 100")
                            continue

                    extra_data = {
                        "target_stage_id": target_stage_id,
                        "lyrics_enabled": lyrics_enabled,
                        "background_media_enabled": background_media_enabled,
                        "preset_id": preset_id,
                        "override": payload.get("override") if isinstance(payload.get("override"), bool) else None,
                        "size_vw": size_vw,
                        "line_width_pct": line_width_pct,
                    }
                    extra_data = {key: value for key, value in extra_data.items() if value is not None}
                    await manager.broadcast_stage_control_command(
                        command=command,
                        source=source,
                        extra_data=extra_data,
                        target_stage_id=target_stage_id,
                    )
                    continue

                if command == "set_background_media_enabled":
                    if not is_admin:
                        await _send_ws_error(websocket, "Admin session required for background settings")
                        continue

                    target_stage_id = await _resolve_target_stage_id(websocket, manager, "Background settings", payload)
                    if not target_stage_id:
                        continue

                    background_media_enabled = payload.get("background_media_enabled")
                    if not isinstance(background_media_enabled, bool):
                        await _send_ws_error(websocket, "set_background_media_enabled requires boolean background_media_enabled")
                        continue

                    await manager.broadcast_stage_control_command(
                        command=command,
                        source=source,
                        extra_data={
                            "target_stage_id": target_stage_id,
                            "background_media_enabled": background_media_enabled,
                        },
                        target_stage_id=target_stage_id,
                    )
                    continue

                if not _can_control_current_stage(
                    db,
                    is_admin=is_admin,
                    requester_id=_websocket_guest_id(websocket),
                ):
                    await _send_ws_error(
                        websocket,
                        "Not allowed to control this stage item",
                    )
                    continue

                if command == "skip":
                    current = queue_service.get_current_item(db)
                    result = queue_service.skip_current_item(db)

                    await manager.broadcast_stage_control_command(command=command, source=source)
                    await manager.broadcast_current_item_changed(
                        result.id if result else None,
                        current.id if current else None,
                    )
                elif command == "seek":
                    raw_seek_time = payload.get("seek_time")
                    if not isinstance(raw_seek_time, (int, float)):
                        await manager.send_personal_message(
                            {
                                "type": "error",
                                "data": {"detail": "seek requires numeric seek_time"},
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            websocket,
                        )
                        continue
                    seek_time = float(raw_seek_time)
                    if seek_time < 0.0 or not math.isfinite(seek_time):
                        await manager.send_personal_message(
                            {
                                "type": "error",
                                "data": {"detail": "seek_time must be a non-negative finite number"},
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            websocket,
                        )
                        continue
                    is_paused = payload.get("is_paused")
                    extra_data = {"seek_time": seek_time}
                    if isinstance(is_paused, bool):
                        extra_data["is_paused"] = is_paused
                    await manager.broadcast_stage_control_command(
                        command=command,
                        source=source,
                        extra_data=extra_data,
                    )
                    await manager.set_stage_current_time(
                        current_time=seek_time,
                        source=source,
                        is_paused=is_paused if isinstance(is_paused, bool) else None,
                        broadcast_state=True,
                    )
                elif command == "seek_relative":
                    raw_offset_seconds = payload.get("offset_seconds")
                    if not isinstance(raw_offset_seconds, (int, float)):
                        await manager.send_personal_message(
                            {
                                "type": "error",
                                "data": {"detail": "seek_relative requires numeric offset_seconds"},
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            websocket,
                        )
                        continue
                    offset_seconds = float(raw_offset_seconds)
                    if not math.isfinite(offset_seconds):
                        await manager.send_personal_message(
                            {
                                "type": "error",
                                "data": {"detail": "offset_seconds must be finite"},
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            websocket,
                        )
                        continue
                    is_paused = payload.get("is_paused")
                    extra_data = {"offset_seconds": offset_seconds}
                    if isinstance(is_paused, bool):
                        extra_data["is_paused"] = is_paused
                    await manager.broadcast_stage_control_command(
                        command=command,
                        source=source,
                        extra_data=extra_data,
                    )
                elif command == "resync":
                    extra_data = {"sync_version": manager.next_stage_sync_version()}
                    raw_seek_time = payload.get("seek_time")
                    if isinstance(raw_seek_time, (int, float)):
                        seek_time = float(raw_seek_time)
                        if seek_time < 0.0 or not math.isfinite(seek_time):
                            await manager.send_personal_message(
                                {
                                    "type": "error",
                                    "data": {"detail": "seek_time must be a non-negative finite number"},
                                    "timestamp": asyncio.get_event_loop().time(),
                                },
                                websocket,
                            )
                            continue
                        extra_data["seek_time"] = seek_time
                    is_paused = payload.get("is_paused")
                    if isinstance(is_paused, bool):
                        extra_data["is_paused"] = is_paused
                    await manager.broadcast_stage_control_command(
                        command=command,
                        source=source,
                        extra_data=extra_data,
                    )
                    if "seek_time" in extra_data:
                        await manager.set_stage_current_time(
                            current_time=extra_data["seek_time"],
                            source=source,
                            is_paused=is_paused if isinstance(is_paused, bool) else None,
                            broadcast_state=True,
                        )
                elif command == "set_vocals_enabled":
                    vocals_enabled = payload.get("vocals_enabled")
                    if not isinstance(vocals_enabled, bool):
                        await manager.send_personal_message(
                            {
                                "type": "error",
                                "data": {"detail": "set_vocals_enabled requires boolean vocals_enabled"},
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            websocket,
                        )
                        continue
                    await manager.set_stage_vocals_enabled(vocals_enabled=vocals_enabled, source=source)
                elif command == "set_vocals_volume":
                    raw_volume = payload.get("vocals_volume")
                    if not isinstance(raw_volume, (int, float)):
                        await manager.send_personal_message(
                            {
                                "type": "error",
                                "data": {"detail": "set_vocals_volume requires numeric vocals_volume"},
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            websocket,
                        )
                        continue
                    volume = float(raw_volume)
                    if volume < 0.0 or volume > 1.0:
                        await manager.send_personal_message(
                            {
                                "type": "error",
                                "data": {"detail": "vocals_volume must be between 0.0 and 1.0"},
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            websocket,
                        )
                        continue
                    await manager.set_stage_vocals_volume(vocals_volume=volume, source=source)
                elif command == "set_lyrics_enabled":
                    lyrics_enabled = payload.get("lyrics_enabled")
                    if not isinstance(lyrics_enabled, bool):
                        await manager.send_personal_message(
                            {
                                "type": "error",
                                "data": {"detail": "set_lyrics_enabled requires boolean lyrics_enabled"},
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            websocket,
                        )
                        continue
                    await manager.set_stage_lyrics_enabled(lyrics_enabled=lyrics_enabled, source=source)
                else:
                    await manager.broadcast_stage_control_command(command=command, source=source)
                    await manager.set_stage_paused(is_paused=(command == "pause"), source=source)
                continue

            if data.get("type") == "stage_time_update":
                if not _is_admin_websocket(websocket, db):
                    await _send_ws_error(
                        websocket,
                        "Admin session required for stage time updates",
                    )
                    continue

                payload = data.get("data")
                if not isinstance(payload, dict):
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": "Invalid stage_time_update payload"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue

                raw_current_time = payload.get("current_time")
                if not isinstance(raw_current_time, (int, float)):
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": "stage_time_update requires numeric current_time"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue
                current_time = float(raw_current_time)
                if current_time < 0.0 or not math.isfinite(current_time):
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": "current_time must be a non-negative finite number"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
                    )
                    continue
                is_paused = payload.get("is_paused")
                if isinstance(is_paused, bool):
                    await manager.set_stage_current_time(
                        current_time=current_time,
                        source=payload.get("source", "stage"),
                        is_paused=is_paused,
                    )
                else:
                    await manager.set_stage_current_time(
                        current_time=current_time,
                        source=payload.get("source", "stage"),
                    )
                continue
            
            # Handle other message types as needed
            logger.debug(f"Received WebSocket message: {data.get('type')}")
    
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
        await manager.disconnect(websocket)
