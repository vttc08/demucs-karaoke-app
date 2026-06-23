"""Data models and database schemas."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Text,
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


class ProcessingTaskStatus(str, Enum):
    """Durable processing task status."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


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
    requested_lyrics_alignment = Column(Boolean, default=False, nullable=False)
    user_id = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    requester_name = Column(String, nullable=True)
    whisperx_align_language_override = Column(String, nullable=True)
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
    processing_tasks = relationship("ProcessingTask", back_populates="media")


class RuntimeSetting(Base):
    """Persisted runtime setting stored as a key/value pair."""

    __tablename__ = "runtime_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LyricsPreset(Base):
    """Persisted stage lyric settings preset."""

    __tablename__ = "lyrics_presets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    settings_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class ProcessingTask(Base):
    """Durable processing task metadata."""

    __tablename__ = "processing_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String, nullable=False, index=True)
    source_kind = Column(String, nullable=False, index=True)
    target_queue_item_id = Column(
        Integer,
        ForeignKey("queue_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    target_media_item_id = Column(
        Integer,
        ForeignKey("media_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    status = Column(String, nullable=False, default=ProcessingTaskStatus.PENDING.value, index=True)
    stage = Column(String, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error_summary = Column(String, nullable=True)
    last_error_detail = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    queue_item = relationship("QueueItem")
    media = relationship("MediaItem", back_populates="processing_tasks")


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
    lyrics_format: Optional[Literal["lrc", "txt", "json"]] = None
    align_lyrics: bool = False
    whisperx_align_language_override: Optional[str] = None
    queue_as_name: Optional[str] = None
    queue_as_guest_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_source(self):
        """Require at least one media source identifier."""
        if isinstance(self.youtube_id, str):
            self.youtube_id = self.youtube_id.strip() or None
        if isinstance(self.lyrics_text, str):
            self.lyrics_text = self.lyrics_text.strip() or None
        if isinstance(self.whisperx_align_language_override, str):
            override = " ".join(self.whisperx_align_language_override.split()).strip().lower()
            self.whisperx_align_language_override = override if override not in {"", "auto", "default"} else None
        if isinstance(self.queue_as_name, str):
            normalized_queue_as = " ".join(self.queue_as_name.split()).strip()
            self.queue_as_name = normalized_queue_as[:40] or None
        if isinstance(self.queue_as_guest_id, str):
            normalized_queue_as_guest_id = " ".join(self.queue_as_guest_id.split()).strip()
            self.queue_as_guest_id = normalized_queue_as_guest_id[:80] or None
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


class ChineseLyricsTransformRequest(BaseModel):
    """Request to simplify Chinese lyrics and optionally add pinyin."""

    texts: list[str]
    include_pinyin: bool = False


class ChineseLyricsTransformItem(BaseModel):
    """Transformed lyrics line for display-only rendering."""

    original: str
    simplified: str
    pinyin: Optional[str] = None
    has_chinese: bool = False


class ChineseLyricsTransformResponse(BaseModel):
    """Display-oriented Chinese lyrics transformation result."""

    items: list[ChineseLyricsTransformItem]


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
    can_control_stage: bool = False
    can_cancel_task: bool = False
    is_karaoke: bool
    status: QueueStatus
    thumbnail: Optional[str] = None
    media_path: Optional[str] = None
    lyrics_path: Optional[str] = None
    vocals_path: Optional[str] = None
    whisperx_align_language_override: Optional[str] = None
    error: Optional[str] = None
    task_id: Optional[int] = None
    processing_stage: Optional[str] = None
    processing_progress: Optional[int] = None
    processing_label: Optional[str] = None
    processing_label_key: Optional[str] = None
    processing_label_args: Optional[dict[str, Any]] = None
    processing_step_index: Optional[int] = None
    processing_step_total: Optional[int] = None
    created_at: datetime


class ProcessingTaskSnapshotResponse(BaseModel):
    """Live in-memory task state."""

    progress_percent: Optional[int] = None
    progress_label: Optional[str] = None
    progress_label_key: Optional[str] = None
    progress_label_args: Optional[dict[str, Any]] = None
    progress_step_index: Optional[int] = None
    progress_step_total: Optional[int] = None
    event_sequence: int = 0
    event_count: int = 0


class MediaTrimRequest(BaseModel):
    """Requested retained interval for a lossless media trim."""

    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")
        return self


class ProcessingTaskResponse(BaseModel):
    """Durable task response enriched with live snapshot when available."""

    id: int
    task_type: str
    source_kind: str
    target_queue_item_id: Optional[int] = None
    target_media_item_id: Optional[int] = None
    status: ProcessingTaskStatus
    stage: Optional[str] = None
    attempt_count: int
    last_error_summary: Optional[str] = None
    last_error_detail: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    live: Optional[ProcessingTaskSnapshotResponse] = None


class ProcessingTaskEventResponse(BaseModel):
    """Live task stream event payload."""

    task_id: int
    event_type: Literal[
        "snapshot",
        "progress",
        "log",
        "stage_changed",
        "status_changed",
        "error",
        "done",
        "canceled",
    ]
    status: Optional[ProcessingTaskStatus] = None
    stage: Optional[str] = None
    progress_percent: Optional[int] = None
    progress_label: Optional[str] = None
    progress_label_key: Optional[str] = None
    progress_label_args: Optional[dict[str, Any]] = None
    progress_step_index: Optional[int] = None
    progress_step_total: Optional[int] = None
    message: Optional[str] = None
    stream: Optional[Literal["system", "stdout", "stderr", "remote"]] = None
    sequence: int
    timestamp: datetime


class RuntimeSettingsResponse(BaseModel):
    """Runtime-editable application settings."""

    demucs_api_url: str
    demucs_healthy: bool
    demucs_health_detail: str
    demucs_model: str
    demucs_device: str
    demucs_output_format: str
    demucs_mp3_bitrate: int
    demucs_direct_media_max_mb: int
    demucs_poll_interval_seconds: float
    whisperx_transcription_model: str
    whisperx_align_language: str | None
    whisperx_detect_language: bool
    whisperx_use_synced_lyrics: bool
    whisperx_preload_models: str | None
    ffmpeg_preset: str
    ffmpeg_crf: int
    ytdlp_path: str
    ytdlp_proxy_url: str
    ytdlp_video_resolution: str
    concurrent_ytdlp_search_enabled: bool
    lyrics_provider_netease_enabled: bool
    lyrics_provider_lrclib_enabled: bool
    ffmpeg_path: str
    media_path: str
    cache_path: str
    stage_qr_url: str
    stage_lobby_media_path: str
    stage_vocals_volume_default: float


class RuntimeSettingsUpdateRequest(BaseModel):
    """Partial update payload for runtime settings."""

    demucs_api_url: Optional[str] = None
    demucs_model: Optional[str] = None
    demucs_device: Optional[str] = None
    demucs_output_format: Optional[str] = None
    demucs_mp3_bitrate: Optional[int] = None
    demucs_direct_media_max_mb: Optional[int] = None
    demucs_poll_interval_seconds: Optional[float] = None
    whisperx_transcription_model: Optional[str] = None
    whisperx_align_language: Optional[str] = None
    whisperx_detect_language: Optional[bool] = None
    whisperx_use_synced_lyrics: Optional[bool] = None
    whisperx_preload_models: Optional[str] = None
    ffmpeg_preset: Optional[str] = None
    ffmpeg_crf: Optional[int] = None
    ytdlp_path: Optional[str] = None
    ytdlp_proxy_url: Optional[str] = None
    ytdlp_video_resolution: Optional[str] = None
    concurrent_ytdlp_search_enabled: Optional[bool] = None
    lyrics_provider_netease_enabled: Optional[bool] = None
    lyrics_provider_lrclib_enabled: Optional[bool] = None
    ffmpeg_path: Optional[str] = None
    media_path: Optional[str] = None
    cache_path: Optional[str] = None
    stage_qr_url: Optional[str] = None
    stage_lobby_media_path: Optional[str] = None
    stage_vocals_volume_default: Optional[float] = None


class LyricsPresetCreateRequest(BaseModel):
    """Request to create a stage lyric preset."""

    name: str
    settings: dict[str, Any]


class LyricsPresetUpdateRequest(BaseModel):
    """Request to update a stage lyric preset."""

    name: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class LyricsPresetResponse(BaseModel):
    """Persisted stage lyric preset."""

    model_config = {"from_attributes": True}

    id: int
    name: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WhisperXPreloadRequest(BaseModel):
    """Request to preload WhisperX models on the remote Demucs host."""

    whisperx_preload_models: Optional[str] = None


class WhisperXPreloadResponse(BaseModel):
    """Result of a WhisperX preload request."""

    requested_models: Optional[str] = None
    device: str
    compute_type: Optional[str] = None
    loaded_entries: list[str]
    detail: str


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


class ProxyInfoRequest(BaseModel):
    """Request to resolve proxy egress information."""

    proxy_url: Optional[str] = None


class ProxyInfoResponse(BaseModel):
    """Public egress information returned through a proxy."""

    ip: str
    org: str
    city: str
    country: str
    detail: str


class DemucsRequest(BaseModel):
    """Request to Demucs service."""

    audio_path: str
    lyrics_text: Optional[str] = None
    lyrics_format: Optional[Literal["lrc", "txt", "json"]] = None
    transcription_model: str = "tiny"
    align_language: Optional[str] = None
    detect_language: bool = False
    use_synced_lyrics: bool = False
    whisperx_preload_models: Optional[str] = None
    compute_type: Optional[str] = None


class DemucsResponse(BaseModel):
    """Response from Demucs service."""

    job_id: Optional[str] = None
    no_vocals_path: str
    vocals_path: Optional[str] = None
    aligned_lyrics_path: Optional[str] = None


class DemucsGarbageCollectionResponse(BaseModel):
    """Response from Demucs garbage collection."""

    requested_mode: Literal["adaptive", "partial", "cuda", "full"]
    executed_mode: Literal["partial", "cuda", "full"]
    triggered_by: Literal["manual", "scheduled", "job_completion"]
    detail: str
    active_job_count: int
    running_job_count: int
    free_vram_bytes: Optional[int] = None
    total_vram_bytes: Optional[int] = None
    python_gc_collected: int
    whisperx_unloaded: dict[str, int] = Field(default_factory=dict)
    cuda_cache_cleared: bool = False
    cuda_ipc_cleared: bool = False
    started_at: str
    finished_at: str


class DemucsHealthResponse(BaseModel):
    """Demucs service health state."""

    api_url: str
    healthy: bool
    detail: str
