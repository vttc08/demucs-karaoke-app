"""Data models and database schemas."""
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, model_validator
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now() -> datetime:
    """Return a naive UTC datetime for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class QueueStatus(str, Enum):
    """Queue item status."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    READY = "ready"
    PLAYING = "playing"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueItem(Base):
    """Queue item database model."""

    __tablename__ = "queue_items"

    id = Column(Integer, primary_key=True, index=True)
    media_id = Column(
        Integer,
        ForeignKey("media_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    position = Column(Integer, nullable=False, index=True)
    requested_karaoke = Column(Boolean, default=False, nullable=False)
    user_id = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    requester_name = Column(String, nullable=True)
    status = Column(String, default=QueueStatus.PENDING)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    media = relationship("MediaItem", back_populates="queue_items")


class MediaItem(Base):
    """Durable media/library item."""

    __tablename__ = "media_items"
    __table_args__ = (
        UniqueConstraint("youtube_id", name="uq_media_items_youtube_id"),
        Index("ix_media_items_youtube_id", "youtube_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    youtube_id = Column(String, nullable=True)
    file_stem = Column(String, nullable=True, index=True)
    title = Column(String, nullable=False, index=True)
    artist = Column(String, nullable=True, index=True)
    media_path = Column(String, nullable=False, unique=True)
    lyrics_path = Column(String, nullable=True)
    vocals_path = Column(String, nullable=True)
    missing = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    last_scanned_at = Column(DateTime, nullable=True)
    queue_items = relationship("QueueItem", back_populates="media")


class RuntimeSetting(Base):
    """Persisted runtime setting stored as a key/value pair."""

    __tablename__ = "runtime_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminUser(Base):
    """Server-managed administrator account."""

    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    password_iterations = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    sessions = relationship(
        "AdminSession", back_populates="admin_user", cascade="all, delete-orphan"
    )


class AdminSession(Base):
    """Persisted administrator login session."""

    __tablename__ = "admin_sessions"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(
        Integer,
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    admin_user = relationship("AdminUser", back_populates="sessions")


# Pydantic models for API
class YouTubeSearchResult(BaseModel):
    """YouTube search result."""

    source: Literal["youtube", "local"] = "youtube"
    media_item_id: Optional[int] = None
    video_id: Optional[str] = None
    title: str
    channel: str
    duration: Optional[str] = None
    thumbnail: Optional[str] = None
    downloaded: bool = False


class QueueItemCreate(BaseModel):
    """Request to add item to queue."""

    youtube_id: Optional[str] = None
    media_item_id: Optional[int] = None
    title: str
    artist: Optional[str] = None
    is_karaoke: bool = False
    lyrics_text: Optional[str] = None
    lyrics_format: Optional[Literal["lrc", "txt"]] = None

    @model_validator(mode="after")
    def validate_source(self):
        """Require at least one media source identifier."""
        if isinstance(self.youtube_id, str):
            self.youtube_id = self.youtube_id.strip() or None
        if isinstance(self.lyrics_text, str):
            self.lyrics_text = self.lyrics_text.strip() or None
        if self.youtube_id is None and self.media_item_id is None:
            raise ValueError("Either youtube_id or media_item_id is required")
        return self


class QueueItemMoveRequest(BaseModel):
    """Request to move a queue item within the active ordering."""

    direction: Literal["up", "down"]


class LyricsResolveRequest(BaseModel):
    """Request to resolve lyrics for queue configuration."""

    title: str
    artist: Optional[str] = None
    youtube_title: Optional[str] = None


class LyricsResolveResponse(BaseModel):
    """Lyrics resolution result for the queue UI."""

    status: Literal["resolved", "not_found"]
    title: str
    artist: Optional[str] = None
    source: str
    provider: Optional[str] = None
    lyrics: Optional[str] = None
    is_synced: bool = False
    detail: Optional[str] = None


class QueueItemResponse(BaseModel):
    """Queue item response."""

    model_config = {"from_attributes": True}

    id: int
    media_id: int
    position: int
    youtube_id: str
    title: str
    artist: Optional[str] = None
    requested_by_name: Optional[str] = None
    can_remove: bool = False
    is_karaoke: bool
    status: QueueStatus
    thumbnail: Optional[str] = None
    media_path: Optional[str] = None
    lyrics_path: Optional[str] = None
    vocals_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime


class RuntimeSettingsResponse(BaseModel):
    """Runtime-editable application settings."""

    demucs_api_url: str
    demucs_healthy: bool
    demucs_health_detail: str
    demucs_model: str
    demucs_device: str
    demucs_output_format: str
    demucs_mp3_bitrate: int
    ffmpeg_preset: str
    ffmpeg_crf: int
    ytdlp_path: str
    ytdlp_proxy_url: str
    concurrent_ytdlp_search_enabled: bool
    lyrics_provider_netease_enabled: bool
    lyrics_provider_lrclib_enabled: bool
    ffmpeg_path: str
    media_path: str
    cache_path: str
    stage_qr_url: str
    stage_lobby_media_path: str


class RuntimeSettingsUpdateRequest(BaseModel):
    """Partial update payload for runtime settings."""

    demucs_api_url: Optional[str] = None
    demucs_model: Optional[str] = None
    demucs_device: Optional[str] = None
    demucs_output_format: Optional[str] = None
    demucs_mp3_bitrate: Optional[int] = None
    ffmpeg_preset: Optional[str] = None
    ffmpeg_crf: Optional[int] = None
    ytdlp_path: Optional[str] = None
    ytdlp_proxy_url: Optional[str] = None
    concurrent_ytdlp_search_enabled: Optional[bool] = None
    lyrics_provider_netease_enabled: Optional[bool] = None
    lyrics_provider_lrclib_enabled: Optional[bool] = None
    ffmpeg_path: Optional[str] = None
    media_path: Optional[str] = None
    cache_path: Optional[str] = None
    stage_qr_url: Optional[str] = None
    stage_lobby_media_path: Optional[str] = None


class YtDlpVersionResponse(BaseModel):
    """yt-dlp version details."""

    version: str
    binary_path: str


class YtDlpUpdateResponse(BaseModel):
    """Result of a yt-dlp self-update attempt."""

    before_version: str
    after_version: str
    updated: bool
    detail: str


class DemucsRequest(BaseModel):
    """Request to Demucs service."""

    audio_path: str


class DemucsResponse(BaseModel):
    """Response from Demucs service."""

    no_vocals_path: str
    vocals_path: Optional[str] = None


class DemucsHealthResponse(BaseModel):
    """Demucs service health state."""

    api_url: str
    healthy: bool
    detail: str
