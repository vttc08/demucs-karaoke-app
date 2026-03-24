"""Queue service for managing the karaoke queue."""
from typing import List, Optional
from sqlalchemy.orm import Session
from models import QueueItem, QueueItemCreate, QueueItemResponse, QueueStatus


class QueueService:
    """Service for queue operations."""

    def add_to_queue(
        self, db: Session, item: QueueItemCreate
    ) -> QueueItemResponse:
        """
        Add item to queue.

        Args:
            db: Database session
            item: Queue item to add

        Returns:
            Created queue item
        """
        db_item = QueueItem(
            youtube_id=item.youtube_id,
            title=item.title,
            artist=item.artist,
            is_karaoke=item.is_karaoke,
            burn_lyrics=(item.burn_lyrics if item.is_karaoke else False),
            status=QueueStatus.PENDING,
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return QueueItemResponse.model_validate(db_item)

    def get_queue(
        self, db: Session, limit: int = 50
    ) -> List[QueueItemResponse]:
        """
        Get all pending and processing items in queue.

        Args:
            db: Database session
            limit: Maximum items to return

        Returns:
            List of queue items
        """
        items = (
            db.query(QueueItem)
            .filter(
                QueueItem.status.in_(
                    [
                        QueueStatus.PENDING,
                        QueueStatus.DOWNLOADING,
                        QueueStatus.PROCESSING,
                        QueueStatus.READY,
                        QueueStatus.PLAYING,
                    ]
                )
            )
            .order_by(QueueItem.id)
            .limit(limit)
            .all()
        )
        return [QueueItemResponse.model_validate(item) for item in items]

    def get_current_item(self, db: Session) -> Optional[QueueItemResponse]:
        """
        Get currently playing item.

        Args:
            db: Database session

        Returns:
            Current queue item or None
        """
        item = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.PLAYING)
            .first()
        )
        return QueueItemResponse.model_validate(item) if item else None

    def get_current_or_promote_next(self, db: Session) -> Optional[QueueItemResponse]:
        """
        Return currently playing item, or promote next READY item to PLAYING.
        """
        current = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.PLAYING)
            .order_by(QueueItem.id)
            .first()
        )
        if current:
            return QueueItemResponse.model_validate(current)

        next_ready = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.READY)
            .order_by(QueueItem.id)
            .first()
        )
        if not next_ready:
            return None

        next_ready.status = QueueStatus.PLAYING
        db.commit()
        db.refresh(next_ready)
        return QueueItemResponse.model_validate(next_ready)

    def get_next_item(self, db: Session) -> Optional[QueueItemResponse]:
        """
        Get next ready item in queue.

        Args:
            db: Database session

        Returns:
            Next queue item or None
        """
        item = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.READY)
            .order_by(QueueItem.id)
            .first()
        )
        return QueueItemResponse.model_validate(item) if item else None

    def skip_current_item(self, db: Session) -> Optional[QueueItemResponse]:
        """
        Skip the currently playing item and promote the next READY item.

        Returns:
            Newly playing queue item, or None if no next item exists.
        """
        current = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.PLAYING)
            .order_by(QueueItem.id)
            .first()
        )

        if current:
            current.status = QueueStatus.COMPLETED

        next_ready = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.READY)
            .order_by(QueueItem.id)
            .first()
        )

        if next_ready:
            next_ready.status = QueueStatus.PLAYING

        if current or next_ready:
            db.commit()

        if not next_ready:
            return None

        db.refresh(next_ready)
        return QueueItemResponse.model_validate(next_ready)

    def complete_current_item(self, db: Session) -> Optional[QueueItemResponse]:
        """
        Mark currently playing item as COMPLETED and promote next READY item.

        Returns:
            Newly playing queue item, or None if no next item exists.
        """
        current = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.PLAYING)
            .order_by(QueueItem.id)
            .first()
        )
        if current:
            current.status = QueueStatus.COMPLETED

        next_ready = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.READY)
            .order_by(QueueItem.id)
            .first()
        )
        if next_ready:
            next_ready.status = QueueStatus.PLAYING

        if current or next_ready:
            db.commit()

        if not next_ready:
            return None

        db.refresh(next_ready)
        return QueueItemResponse.model_validate(next_ready)

    def update_status(
        self, db: Session, item_id: int, status: QueueStatus, error: str = None
    ):
        """
        Update item status.

        Args:
            db: Database session
            item_id: Queue item ID
            status: New status
            error: Error message if status is FAILED
        """
        item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
        if item:
            item.status = status
            if error:
                item.error = error
            db.commit()

    def set_media_path(self, db: Session, item_id: int, media_path: str):
        """
        Set media path for queue item.

        Args:
            db: Database session
            item_id: Queue item ID
            media_path: Path to processed media file
        """
        item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
        if item:
            item.media_path = media_path
            db.commit()

    def set_lyrics(self, db: Session, item_id: int, lyrics: str):
        """
        Set lyrics for queue item.

        Args:
            db: Database session
            item_id: Queue item ID
            lyrics: Lyrics text
        """
        item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
        if item:
            item.lyrics = lyrics
            db.commit()
