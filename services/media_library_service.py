"""Media library query helpers for the media management page."""
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import MediaItem


class MediaLibraryService:
    """Service for read-only media library page data."""

    def list_media_items(self, db: Session) -> list[dict[str, Any]]:
        rows = (
            db.query(MediaItem)
            .order_by(MediaItem.updated_at.desc(), MediaItem.id.desc())
            .all()
        )
        return [self._to_page_item(row) for row in rows]

    def get_media_stats(self, db: Session) -> dict[str, int]:
        total = int(db.query(func.count(MediaItem.id)).scalar() or 0)
        with_multi_track = int(
            db.query(func.count(MediaItem.id))
            .filter(MediaItem.vocals_path.isnot(None), MediaItem.vocals_path != "")
            .scalar()
            or 0
        )
        with_lyrics = int(
            db.query(func.count(MediaItem.id))
            .filter(MediaItem.lyrics_path.isnot(None), MediaItem.lyrics_path != "")
            .scalar()
            or 0
        )
        missing = int(
            db.query(func.count(MediaItem.id)).filter(MediaItem.missing.is_(True)).scalar()
            or 0
        )
        return {
            "total": total,
            "with_multi_track": with_multi_track,
            "with_lyrics": with_lyrics,
            "missing": missing,
        }

    @staticmethod
    def _to_page_item(item: MediaItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "title": item.title,
            "artist": item.artist,
            "media_path": item.media_path,
            "status": "missing" if item.missing else "synced",
            "thumbnail": MediaLibraryService._thumbnail_for(item.youtube_id),
            "has_multi_track": bool(item.vocals_path and item.vocals_path.strip()),
            "has_lyrics": bool(item.lyrics_path and item.lyrics_path.strip()),
        }

    @staticmethod
    def _thumbnail_for(youtube_id: str | None) -> str | None:
        if not youtube_id:
            return None
        value = youtube_id.strip()
        if not value:
            return None
        return f"https://i.ytimg.com/vi/{value}/hqdefault.jpg"
