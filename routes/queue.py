"""API routes for queue management."""
import asyncio
import logging
from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from database import SessionLocal, get_db
from models import QueueItemCreate, QueueItemResponse, QueueStatus
from services.queue_service import QueueService
from services.websocket_manager import manager
from models import QueueItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/queue", tags=["queue"])
queue_service = QueueService()


def _process_item_background(item_id: int):
    """Process queue item in a dedicated background session."""
    from services.karaoke_service import KaraokeService

    db = SessionLocal()
    heartbeat_task: asyncio.Task | None = None
    try:
        karaoke_service = KaraokeService()
        asyncio.run(karaoke_service.process_queue_item(db, item_id))
    finally:
        db.close()


@router.post("/", response_model=QueueItemResponse)
async def add_to_queue(item: QueueItemCreate, db: Session = Depends(get_db)):
    """Add item to queue."""
    response = queue_service.add_to_queue(db, item)
    # Broadcast immediately after adding
    await manager.broadcast_queue_item_added(response.model_dump(mode="json"))
    return response


@router.get("/", response_model=List[QueueItemResponse])
def get_queue(db: Session = Depends(get_db)):
    """Get all items in queue."""
    return queue_service.get_queue(db)


@router.get("/current", response_model=QueueItemResponse | None)
def get_current(db: Session = Depends(get_db)):
    """Get currently playing item."""
    return queue_service.get_current_item(db)


@router.get("/next", response_model=QueueItemResponse | None)
def get_next(db: Session = Depends(get_db)):
    """Get next item in queue."""
    return queue_service.get_next_item(db)


@router.post("/skip", response_model=QueueItemResponse | None)
async def skip_current(db: Session = Depends(get_db)):
    """Skip current item and promote next ready item to playing."""
    current = queue_service.get_current_item(db)
    result = queue_service.skip_current_item(db)

    await manager.broadcast_current_item_changed(
        result.id if result else None,
        current.id if current else None,
    )

    return result


@router.post("/complete-current", response_model=QueueItemResponse | None)
async def complete_current(db: Session = Depends(get_db)):
    """Complete current item and promote next ready item to playing."""
    current = queue_service.get_current_item(db)
    result = queue_service.complete_current_item(db)

    await manager.broadcast_current_item_changed(
        result.id if result else None,
        current.id if current else None,
    )

    return result


@router.post("/skip-to/{item_id}", response_model=QueueItemResponse | None)
async def skip_to_item(item_id: int, db: Session = Depends(get_db)):
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


@router.delete("/{item_id}")
async def remove_item(item_id: int, db: Session = Depends(get_db)):
    """Remove an item from the queue."""
    item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    
    if item.status == "playing":
        raise HTTPException(status_code=400, detail="Cannot remove currently playing item")
    
    db.delete(item)
    db.commit()
    
    # Broadcast removal
    await manager.broadcast_queue_item_removed(item_id)
    
    return {"status": "removed", "item_id": item_id}


@router.post("/clear")
async def clear_queue(db: Session = Depends(get_db)):
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger processing of a queue item without blocking the request."""
    item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    if item.status in [QueueStatus.DOWNLOADING, QueueStatus.PROCESSING]:
        return {"status": "processing", "item_id": item_id}

    background_tasks.add_task(_process_item_background, item_id)
    return {"status": "processing", "item_id": item_id}


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
            while True:
                try:
                    await asyncio.sleep(30)
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
            
            # Handle pong response
            if data.get("type") == "pong":
                logger.debug("Received pong from client")
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
                if command not in {"play", "pause", "skip", "set_vocals_enabled", "set_vocals_volume"}:
                    await manager.send_personal_message(
                        {
                            "type": "error",
                            "data": {"detail": f"Unsupported stage command: {command}"},
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                        websocket,
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
                else:
                    await manager.broadcast_stage_control_command(command=command, source=source)
                    await manager.set_stage_paused(is_paused=(command == "pause"), source=source)
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
