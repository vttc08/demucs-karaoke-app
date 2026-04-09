"""Queue service for managing the karaoke queue."""
import logging
from pathlib import Path
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import MediaItem, QueueItem, QueueItemCreate, QueueItemResponse, QueueStatus
from config import settings

logger = logging.getLogger(__name__)
_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm"}
_LYRICS_SUFFIXES = {".lrc", ".srt", ".txt"}


class QueueService:
    """Service for queue operations."""
    POSITION_STEP = 1000

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
        media_item = None
        if item.media_item_id is not None:
            media_item = (
                db.query(MediaItem)
                .filter(MediaItem.id == item.media_item_id)
                .first()
            )
            if media_item is None:
                raise ValueError(f"Media item not found: {item.media_item_id}")
        elif item.youtube_id:
            media_item = (
                db.query(MediaItem)
                .filter(MediaItem.youtube_id == item.youtube_id)
                .first()
            )
            if media_item is None:
                media_item = MediaItem(
                    youtube_id=item.youtube_id,
                    title=item.title,
                    artist=item.artist,
                    media_path=f"/media/{item.youtube_id}.mp4",
                    missing=True,
                )
                db.add(media_item)
                db.flush()
        else:
            raise ValueError("Either youtube_id or media_item_id is required")

        if not media_item.title and item.title:
            media_item.title = item.title
        if not media_item.artist and item.artist:
            media_item.artist = item.artist

        db_item = QueueItem(
            media_id=media_item.id,
            position=self.append_to_end(db),
            requested_karaoke=item.is_karaoke,
            requested_burn_lyrics=(item.burn_lyrics if item.is_karaoke else False),
            status=QueueStatus.PENDING,
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)

        return self._to_response(db_item)

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
                        QueueStatus.FAILED,
                    ]
                )
            )
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .limit(limit)
            .all()
        )
        return [self._to_response(item) for item in items]

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
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )
        return self._to_response(item) if item else None

    def get_current_or_promote_next(self, db: Session) -> Optional[QueueItemResponse]:
        """
        Return currently playing item, or promote next READY item to PLAYING.
        """
        current = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.PLAYING)
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )
        if current:
            return self._to_response(current)

        next_ready = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.READY)
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )
        if not next_ready:
            return None

        next_ready.status = QueueStatus.PLAYING
        db.commit()
        db.refresh(next_ready)

        return self._to_response(next_ready)

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
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )
        return self._to_response(item) if item else None

    def skip_current_item(self, db: Session) -> Optional[QueueItemResponse]:
        """
        Skip the currently playing item and promote the next READY item.

        Returns:
            Newly playing queue item, or None if no next item exists.
        """
        current = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.PLAYING)
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )

        next_ready = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.READY)
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )

        if next_ready:
            next_ready.status = QueueStatus.PLAYING

        if current:
            db.delete(current)

        if current or next_ready:
            db.commit()

        if not next_ready:
            return None

        db.refresh(next_ready)

        return self._to_response(next_ready)

    def complete_current_item(self, db: Session) -> Optional[QueueItemResponse]:
        """
        Mark currently playing item as COMPLETED and promote next READY item.

        Returns:
            Newly playing queue item, or None if no next item exists.
        """
        current = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.PLAYING)
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )

        next_ready = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.READY)
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )
        if next_ready:
            next_ready.status = QueueStatus.PLAYING

        if current:
            db.delete(current)

        if current or next_ready:
            db.commit()

        if not next_ready:
            return None

        db.refresh(next_ready)

        return self._to_response(next_ready)

    async def update_status_async(
        self, db: Session, item_id: int, status: QueueStatus, error: str = None
    ):
        """
        Update item status (async version for use from async contexts).

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
            db.refresh(item)

            # Broadcast the status update
            from services.websocket_manager import manager
            response = self._to_response(item)

            if status == QueueStatus.FAILED and error:
                await manager.broadcast_queue_item_failed(item_id, error)
            else:
                await manager.broadcast_queue_item_updated(
                    response.model_dump(mode="json")
                )

    def update_status(
        self, db: Session, item_id: int, status: QueueStatus, error: str = None
    ):
        """
        Update item status (sync wrapper).

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
            db.refresh(item)

    def set_media_path(self, db: Session, item_id: int, media_path: str):
        """
        Set media path for queue item.

        Args:
            db: Database session
            item_id: Queue item ID
            media_path: Path to processed media file
        """
        item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
        if item and item.media:
            item.media.media_path = self.build_media_url(Path(media_path))
            item.media.missing = False
            db.commit()

    def set_lyrics_path(self, db: Session, item_id: int, lyrics_path: str):
        """Set lyrics sidecar path for media item."""
        item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
        if item and item.media:
            try:
                item.media.lyrics_path = self.build_media_url(Path(lyrics_path))
            except ValueError:
                logger.warning("Skipping non-local lyrics path item_id=%s path=%s", item_id, lyrics_path)
            db.commit()

    def set_vocals_path(self, db: Session, item_id: int, vocals_path: str):
        """Set vocals sidecar path for media item."""
        item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
        if item and item.media:
            try:
                item.media.vocals_path = self.build_media_url(Path(vocals_path))
            except ValueError:
                logger.warning("Skipping non-local vocals path item_id=%s path=%s", item_id, vocals_path)
            db.commit()

    def append_to_end(self, db: Session) -> int:
        """Return a sparse position value at queue tail."""
        max_position = db.query(func.max(QueueItem.position)).scalar()
        if max_position is None:
            return self.POSITION_STEP
        return int(max_position) + self.POSITION_STEP

    def add_to_front(self, db: Session) -> int:
        """Return a sparse position value at queue head."""
        min_position = db.query(func.min(QueueItem.position)).scalar()
        if min_position is None:
            return self.POSITION_STEP
        if int(min_position) <= self.POSITION_STEP:
            self.renumber_queue_if_needed(db, force=True)
            return self.POSITION_STEP // 2
        new_position = int(min_position) - self.POSITION_STEP
        return new_position

    def insert_between(self, db: Session, before_position: int, after_position: int) -> int:
        """Return a position value between two sparse positions."""
        if before_position >= after_position:
            raise ValueError("before_position must be less than after_position")
        gap = after_position - before_position
        if gap <= 1:
            self.renumber_queue_if_needed(db, force=True)
            raise ValueError("No insert gap available; queue renumbered")
        return before_position + (gap // 2)

    def renumber_queue_if_needed(self, db: Session, force: bool = False):
        """Renumber queue positions when gaps are exhausted."""
        items = (
            db.query(QueueItem)
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .all()
        )
        if not items:
            return

        should_renumber = force
        if not force:
            for index in range(1, len(items)):
                if (items[index].position - items[index - 1].position) <= 1:
                    should_renumber = True
                    break

        if not should_renumber:
            return

        for index, item in enumerate(items, start=1):
            item.position = index * self.POSITION_STEP
        db.commit()

    def _to_response(self, item: QueueItem) -> QueueItemResponse:
        """Map queue row + related media row into API response."""
        media = item.media
        if media is None:
            raise RuntimeError(f"Queue item {item.id} is missing media relationship")

        media_path = self._normalize_media_field(media.media_path)
        vocals_path = self._normalize_media_field(media.vocals_path)
        lyrics_path = self._normalize_media_field(media.lyrics_path)
        vocals_path, lyrics_path = self._repair_sidecar_fields(
            media_path=media_path,
            vocals_path=vocals_path,
            lyrics_path=lyrics_path,
        )
        return QueueItemResponse(
            id=item.id,
            media_id=media.id,
            position=item.position,
            youtube_id=media.youtube_id or "",
            title=media.title,
            artist=media.artist,
            is_karaoke=bool(item.requested_karaoke),
            burn_lyrics=bool(item.requested_burn_lyrics),
            status=QueueStatus(item.status),
            media_path=media_path,
            lyrics_path=lyrics_path,
            vocals_path=vocals_path,
            error=item.error,
            created_at=item.created_at,
        )

    def _normalize_media_field(self, raw_path: str | None) -> str | None:
        """Normalize persisted path values into URLs the app can actually serve."""
        if raw_path is None:
            return None

        value = raw_path.strip()
        if not value:
            return None

        if value.startswith(("http://", "https://", "/media/", "/cache/")):
            return value

        try:
            return self.build_media_url(Path(value))
        except ValueError:
            logger.warning("Unservable media field path=%s", value)
            return None

    def _repair_sidecar_fields(
        self, media_path: str | None, vocals_path: str | None, lyrics_path: str | None
    ) -> tuple[str | None, str | None]:
        """
        Normalize common sidecar mistakes and infer vocals sidecar when possible.

        - If vocals_path points to a lyrics file, move it to lyrics_path.
        - If vocals_path is missing, probe sibling *.vocals.<audio_ext> files.
        """
        def classify(path_value: str | None) -> str:
            if not path_value:
                return "missing"
            suffix = Path(path_value).suffix.lower()
            if suffix in _AUDIO_SUFFIXES:
                return "audio"
            if suffix in _LYRICS_SUFFIXES:
                return "lyrics"
            return "other"

        vocals_kind = classify(vocals_path)
        lyrics_kind = classify(lyrics_path)

        if vocals_kind == "lyrics" and lyrics_kind == "audio":
            vocals_path, lyrics_path = lyrics_path, vocals_path
            vocals_kind, lyrics_kind = "audio", "lyrics"
        elif vocals_kind == "lyrics":
            if lyrics_kind == "missing":
                lyrics_path = vocals_path
                lyrics_kind = "lyrics"
            vocals_path = None
            vocals_kind = "missing"

        if lyrics_kind == "audio":
            if vocals_kind in {"missing", "other"}:
                vocals_path = lyrics_path
                vocals_kind = "audio"
            lyrics_path = None
            lyrics_kind = "missing"

        if vocals_kind == "other":
            vocals_path = None

        if vocals_path:
            return vocals_path, lyrics_path

        media_file = self._media_url_to_file(media_path)
        if media_file is None:
            return vocals_path, lyrics_path

        stem = media_file.stem
        for ext in (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm"):
            candidate = media_file.with_name(f"{stem}.vocals{ext}")
            if candidate.exists():
                try:
                    vocals_path = self.build_media_url(candidate)
                    break
                except ValueError:
                    logger.warning("Found vocals sidecar outside served roots path=%s", candidate)
                    break

        if not lyrics_path:
            for ext in (".lrc", ".srt", ".txt"):
                candidate = media_file.with_suffix(ext)
                if candidate.exists():
                    try:
                        lyrics_path = self.build_media_url(candidate)
                    except ValueError:
                        logger.warning("Found lyrics sidecar outside served roots path=%s", candidate)
                    break

        return vocals_path, lyrics_path

    @staticmethod
    def _media_url_to_file(media_url: str | None) -> Path | None:
        """Map a /media or /cache URL back to local filesystem path."""
        if not media_url:
            return None
        if media_url.startswith("/media/"):
            relative = media_url.removeprefix("/media/")
            return settings.media_path / relative
        if media_url.startswith("/cache/"):
            relative = media_url.removeprefix("/cache/")
            return settings.cache_path / relative
        return None
    @staticmethod
    def build_media_url(file_path: Path) -> str:
        """Build a stable API URL for files under configured media/cache roots."""
        resolved = file_path.resolve()
        media_root = settings.media_path.resolve()
        cache_root = settings.cache_path.resolve()

        try:
            relative = resolved.relative_to(media_root)
            return f"/media/{relative.as_posix()}"
        except ValueError:
            pass

        try:
            relative = resolved.relative_to(cache_root)
            return f"/cache/{relative.as_posix()}"
        except ValueError:
            pass

        raise ValueError(f"File path is outside media/cache roots: {file_path}")
