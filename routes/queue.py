"""API routes for queue management."""
import asyncio
from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal, get_db
from models import QueueItemCreate, QueueItemResponse, QueueStatus
from services.queue_service import QueueService
from models import QueueItem

router = APIRouter(prefix="/api/queue", tags=["queue"])
queue_service = QueueService()


def _process_item_background(item_id: int):
    """Process queue item in a dedicated background session."""
    from services.karaoke_service import KaraokeService

    db = SessionLocal()
    try:
        karaoke_service = KaraokeService()
        asyncio.run(karaoke_service.process_queue_item(db, item_id))
    finally:
        db.close()


@router.post("/", response_model=QueueItemResponse)
def add_to_queue(item: QueueItemCreate, db: Session = Depends(get_db)):
    """Add item to queue."""
    return queue_service.add_to_queue(db, item)


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
def skip_current(db: Session = Depends(get_db)):
    """Skip current item and promote next ready item to playing."""
    return queue_service.skip_current_item(db)


@router.post("/complete-current", response_model=QueueItemResponse | None)
def complete_current(db: Session = Depends(get_db)):
    """Complete current item and promote next ready item to playing."""
    return queue_service.complete_current_item(db)


@router.post("/skip-to/{item_id}", response_model=QueueItemResponse | None)
def skip_to_item(item_id: int, db: Session = Depends(get_db)):
    """Skip to a specific item in the queue."""
    item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    
    if item.status != "ready":
        raise HTTPException(status_code=400, detail="Item is not ready for playback")
    
    # Complete current item and set the target item as playing
    current = queue_service.get_current_item(db)
    if current:
        queue_service.complete_current_item(db)
    
    # Set target item as playing
    item.status = "playing"
    db.commit()
    db.refresh(item)
    
    return QueueItemResponse.from_orm(item)


@router.delete("/{item_id}")
def remove_item(item_id: int, db: Session = Depends(get_db)):
    """Remove an item from the queue."""
    item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    
    if item.status == "playing":
        raise HTTPException(status_code=400, detail="Cannot remove currently playing item")
    
    db.delete(item)
    db.commit()
    
    return {"status": "removed", "item_id": item_id}


@router.post("/clear")
def clear_queue(db: Session = Depends(get_db)):
    """Clear all items from the queue except currently playing."""
    # Remove all items except the currently playing one
    db.query(QueueItem).filter(QueueItem.status != "playing").delete()
    db.commit()
    
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
