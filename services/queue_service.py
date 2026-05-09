"""Queue service for managing the karaoke queue."""
import logging
import re
import shutil
from pathlib import Path
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import MediaItem, QueueItem, QueueItemCreate, QueueItemResponse, QueueStatus
from config import settings
from services.media_naming import build_media_stem

logger = logging.getLogger(__name__)
_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".webm"}
_LYRICS_SUFFIXES = {".lrc", ".srt", ".txt"}


class QueueService:
    """Service for queue operations."""
    POSITION_STEP = 1000
    ACTIVE_QUEUE_STATUSES = (
        QueueStatus.PENDING,
        QueueStatus.DOWNLOADING,
        QueueStatus.PROCESSING,
        QueueStatus.READY,
        QueueStatus.PLAYING,
        QueueStatus.FAILED,
    )

    def add_to_queue(
        self,
        db: Session,
        item: QueueItemCreate,
        *,
        requester_id: str | None = None,
        requester_session_id: str | None = None,
        requester_name: str | None = None,
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
            effective_title = item.title or (media_item.title if media_item else "")
            effective_artist = (
                item.artist
                if item.artist is not None
                else (media_item.artist if media_item else None)
            )
            target_stem = self._allocate_media_stem(
                db,
                build_media_stem(
                    effective_title,
                    effective_artist,
                    fallback=item.youtube_id,
                ),
                item.youtube_id,
                media_item.id if media_item else None,
            )
            if media_item is None:
                media_item = MediaItem(
                    youtube_id=item.youtube_id,
                    title=self._normalize_required_metadata(item.title),
                    artist=self._normalize_optional_metadata(item.artist),
                    file_stem=target_stem,
                    media_path=f"/media/{target_stem}.mp4",
                    missing=True,
                )
                db.add(media_item)
                db.flush()
            else:
                if item.title:
                    media_item.title = self._normalize_required_metadata(item.title)
                if item.artist is not None:
                    media_item.artist = self._normalize_optional_metadata(item.artist)
                self._rehome_media_item_assets(db, media_item, target_stem)
        else:
            raise ValueError("Either youtube_id or media_item_id is required")

        if not media_item.title and item.title:
            media_item.title = item.title
        if not media_item.artist and item.artist:
            media_item.artist = item.artist
        if not media_item.file_stem:
            media_item.file_stem = self._allocate_media_stem(
                db,
                build_media_stem(media_item.title, media_item.artist, fallback=media_item.youtube_id),
                media_item.youtube_id,
                media_item.id,
            )
        if item.is_karaoke and item.lyrics_text:
            self.store_lyrics_sidecar(
                media_item,
                item.lyrics_text,
                lyrics_format=item.lyrics_format,
            )

        db_item = QueueItem(
            media_id=media_item.id,
            position=self.append_to_end(db),
            requested_karaoke=item.is_karaoke,
            user_id=self._normalize_optional_metadata(requester_id),
            session_id=self._normalize_optional_metadata(requester_session_id),
            requester_name=self._normalize_optional_metadata(requester_name),
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
        items = self._get_active_queue_items(db, limit=limit)
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

    def move_queue_item(
        self, db: Session, item_id: int, direction: str
    ) -> QueueItemResponse:
        """Move an active queue item up or down within the non-playing order."""
        if direction not in {"up", "down"}:
            raise ValueError("direction must be 'up' or 'down'")

        for _attempt in range(2):
            items = self._get_active_queue_items(db)
            item = next((candidate for candidate in items if candidate.id == item_id), None)
            if item is None:
                raise ValueError(f"Queue item not found: {item_id}")
            if item.status == QueueStatus.PLAYING:
                raise ValueError("Cannot reorder currently playing item")

            movable_items = [
                candidate for candidate in items if candidate.status != QueueStatus.PLAYING
            ]
            movable_index_by_id = {
                candidate.id: index for index, candidate in enumerate(movable_items)
            }
            movable_index = movable_index_by_id.get(item.id)
            if movable_index is None:
                raise ValueError(f"Queue item not found: {item_id}")

            active_index_by_id = {candidate.id: index for index, candidate in enumerate(items)}

            try:
                if direction == "up":
                    if movable_index == 0:
                        raise ValueError("Item is already at the top of the queue")
                    previous_item = movable_items[movable_index - 1]
                    previous_active_index = active_index_by_id[previous_item.id]
                    before_item = items[previous_active_index - 1] if previous_active_index > 0 else None
                    if before_item is None:
                        item.position = self.add_to_front(db)
                    else:
                        item.position = self.insert_between(db, before_item.position, previous_item.position)
                else:
                    if movable_index == len(movable_items) - 1:
                        raise ValueError("Item is already at the bottom of the queue")
                    next_item = movable_items[movable_index + 1]
                    next_active_index = active_index_by_id[next_item.id]
                    after_item = items[next_active_index + 1] if next_active_index + 1 < len(items) else None
                    if after_item is None:
                        item.position = self.append_to_end(db)
                    else:
                        item.position = self.insert_between(db, next_item.position, after_item.position)
            except ValueError as exc:
                if "No insert gap available" in str(exc) and _attempt == 0:
                    self.renumber_queue_if_needed(db, force=True)
                    continue
                raise

            db.commit()
            db.refresh(item)
            return self._to_response(item)

        raise ValueError("Unable to move queue item")

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

    def promote_next_ready_if_idle(self, db: Session) -> Optional[QueueItemResponse]:
        """Promote the next READY item to PLAYING when no PLAYING item exists."""
        current = (
            db.query(QueueItem)
            .filter(QueueItem.status == QueueStatus.PLAYING)
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
            .first()
        )
        if current:
            return None

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

            if status == QueueStatus.READY:
                promoted = self.promote_next_ready_if_idle(db)
                if promoted:
                    await manager.broadcast_current_item_changed(promoted.id, None)

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

    def store_lyrics_sidecar(
        self,
        media_item: MediaItem,
        lyrics_text: str | None,
        lyrics_format: str | None = None,
        storage: str = "cache",
    ) -> None:
        """Persist lyrics text as a reusable sidecar for a media item."""
        lyrics_text = (lyrics_text or "").strip()
        if not lyrics_text:
            return

        suffix = self._lyrics_suffix(lyrics_text, lyrics_format)
        if storage == "media":
            media_file = self._media_url_to_file(media_item.media_path)
            if media_file is None:
                raise ValueError(f"Cannot store media lyrics sidecar for path: {media_item.media_path}")
            lyrics_path = media_file.with_suffix(suffix)
        elif storage == "cache":
            stem = media_item.file_stem or build_media_stem(
                media_item.title,
                media_item.artist,
                fallback=media_item.youtube_id,
            )
            lyrics_path = settings.cache_path / "lyrics" / f"{stem}{suffix}"
        else:
            raise ValueError("lyrics sidecar storage must be 'cache' or 'media'")

        lyrics_path.parent.mkdir(parents=True, exist_ok=True)
        lyrics_path.write_text(lyrics_text, encoding="utf-8")
        media_item.lyrics_path = self.build_media_url(lyrics_path)
        logger.debug(
            "Stored lyrics sidecar title=%r path=%s format=%s",
            media_item.title,
            lyrics_path,
            suffix,
        )

    @staticmethod
    def _sanitize_sidecar_stem(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
        return cleaned or "lyrics"

    @staticmethod
    def _lyrics_suffix(lyrics_text: str, requested_format: str | None) -> str:
        if requested_format == "lrc":
            return ".lrc"
        if requested_format == "txt":
            return ".txt"
        if re.search(r"^\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]", lyrics_text, re.MULTILINE):
            return ".lrc"
        return ".txt"

    @staticmethod
    def _allocate_media_stem(
        db: Session,
        base_stem: str,
        youtube_id: str | None,
        media_id: int | None,
    ) -> str:
        candidate = base_stem
        if not QueueService._media_stem_in_use(db, candidate, media_id):
            return candidate
        if youtube_id:
            candidate = f"{base_stem} [{youtube_id}]"
        return candidate

    @staticmethod
    def _media_stem_in_use(db: Session, stem: str, media_id: int | None) -> bool:
        query = db.query(MediaItem)
        if media_id is not None:
            query = query.filter(MediaItem.id != media_id)
        for media_item in query.all():
            for media_url in (media_item.media_path, media_item.lyrics_path, media_item.vocals_path):
                media_file = QueueService._media_url_to_file(media_url)
                if media_file and media_file.name.startswith(stem):
                    return True
        return False

    def _rehome_media_item_assets(
        self, db: Session, media_item: MediaItem, target_stem: str
    ) -> None:
        if not target_stem:
            return

        normalized_vocals_path, normalized_lyrics_path = self._repair_sidecar_fields(
            media_path=media_item.media_path,
            vocals_path=media_item.vocals_path,
            lyrics_path=media_item.lyrics_path,
        )

        updated_media_path = self._rename_media_url_field(
            media_item.media_path,
            target_stem,
            media_kind="media",
            target_root=settings.media_path,
        )
        if updated_media_path:
            media_item.media_path = updated_media_path
            media_item.missing = False

        updated_vocals_path = self._rename_media_url_field(
            normalized_vocals_path,
            target_stem,
            media_kind="vocals",
            target_root=settings.media_path,
        )
        if updated_vocals_path:
            media_item.vocals_path = updated_vocals_path

        updated_lyrics_path = self._rename_media_url_field(
            normalized_lyrics_path,
            target_stem,
            media_kind="lyrics",
            target_root=None,
        )
        if updated_lyrics_path:
            media_item.lyrics_path = updated_lyrics_path

        media_item.file_stem = target_stem
        db.flush()

    def _rename_media_url_field(
        self,
        media_url: str | None,
        target_stem: str,
        media_kind: str,
        target_root: Path | None = None,
    ) -> str | None:
        source_path = self._media_url_to_file(media_url)
        if source_path is None or not source_path.exists():
            return media_url

        if media_kind == "vocals":
            target_name = f"{target_stem}.vocals{source_path.suffix}"
        else:
            target_name = f"{target_stem}{source_path.suffix}"
        target_path = (
            (target_root or source_path.parent) / target_name
            if target_root is not None
            else source_path.with_name(target_name)
        )
        if source_path == target_path:
            return media_url

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            if source_path.parent != target_path.parent and source_path.exists():
                source_path.unlink()
                return self.build_media_url(target_path)
            logger.warning(
                "Skipping media rename due to existing target path source=%s target=%s",
                source_path,
                target_path,
            )
            return media_url

        shutil.move(str(source_path), str(target_path))
        return self.build_media_url(target_path)

    @staticmethod
    def _normalize_required_metadata(value: str) -> str:
        cleaned = value.strip()
        return cleaned or value

    @staticmethod
    def _normalize_optional_metadata(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def append_to_end(self, db: Session) -> int:
        """Return a sparse position value at queue tail."""
        max_position = db.query(func.max(QueueItem.position)).scalar()
        if max_position is None:
            return self.POSITION_STEP
        return int(max_position) + self.POSITION_STEP

    def _get_active_queue_items(self, db: Session, limit: int | None = None) -> list[QueueItem]:
        query = (
            db.query(QueueItem)
            .filter(QueueItem.status.in_(self.ACTIVE_QUEUE_STATUSES))
            .order_by(QueueItem.position.asc(), QueueItem.id.asc())
        )
        if limit is not None:
            query = query.limit(limit)
        return query.all()

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
            requested_by_name=item.requester_name,
            is_karaoke=bool(item.requested_karaoke),
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
