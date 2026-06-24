from typing import Literal
from pydantic import BaseModel, Field, model_validator
try:
    from .settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_MP3_BITRATE,
        DEFAULT_OUTPUT_FORMAT,
        DEFAULT_WHISPERX_ALIGN_LANGUAGE,
        DEFAULT_WHISPERX_DETECT_LANGUAGE,
        DEFAULT_WHISPERX_PRELOAD_MODELS,
        DEFAULT_WHISPERX_TRANSCRIPTION_MODEL,
        DEFAULT_WHISPERX_USE_SYNCED_LYRICS,
    )
except ImportError:
    from settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_MP3_BITRATE,
        DEFAULT_OUTPUT_FORMAT,
        DEFAULT_WHISPERX_ALIGN_LANGUAGE,
        DEFAULT_WHISPERX_DETECT_LANGUAGE,
        DEFAULT_WHISPERX_PRELOAD_MODELS,
        DEFAULT_WHISPERX_TRANSCRIPTION_MODEL,
        DEFAULT_WHISPERX_USE_SYNCED_LYRICS,
    )


class SeparateConfig(BaseModel):
    model: str = DEFAULT_DEMUCS_MODEL
    device: Literal["cuda", "cpu"] = DEFAULT_DEMUCS_DEVICE
    output_format: Literal["wav", "mp3"] = DEFAULT_OUTPUT_FORMAT
    mp3_bitrate: int | None = Field(default=None, ge=64, le=320)
    lyrics_text: str | None = None
    lyrics_format: Literal["lrc", "srt", "txt"] | None = None
    transcription_model: str = DEFAULT_WHISPERX_TRANSCRIPTION_MODEL
    align_language: str | None = DEFAULT_WHISPERX_ALIGN_LANGUAGE
    detect_language: bool = DEFAULT_WHISPERX_DETECT_LANGUAGE
    use_synced_lyrics: bool = DEFAULT_WHISPERX_USE_SYNCED_LYRICS
    whisperx_preload_models: str | None = DEFAULT_WHISPERX_PRELOAD_MODELS
    compute_type: str | None = None

    @model_validator(mode="after")
    def validate_mp3_config(self):
        if self.output_format == "mp3" and self.mp3_bitrate is None:
            self.mp3_bitrate = DEFAULT_MP3_BITRATE
        if self.output_format == "wav":
            self.mp3_bitrate = None
        if isinstance(self.lyrics_text, str):
            self.lyrics_text = self.lyrics_text.strip() or None
        if isinstance(self.align_language, str):
            normalized_align_language = self.align_language.strip().lower()
            self.align_language = normalized_align_language or None
        if isinstance(self.transcription_model, str):
            self.transcription_model = self.transcription_model.strip() or DEFAULT_WHISPERX_TRANSCRIPTION_MODEL
        if isinstance(self.whisperx_preload_models, str):
            normalized_preload_models = self.whisperx_preload_models.strip()
            self.whisperx_preload_models = normalized_preload_models or None
        if isinstance(self.compute_type, str):
            normalized_compute_type = self.compute_type.strip().lower()
            self.compute_type = normalized_compute_type or None
        return self


class SeparateMetaResponse(BaseModel):
    job_id: str
    no_vocals_path: str
    vocals_path: str
    model: str
    device: str
    output_format: str
    mp3_bitrate: int | None = None
    duration_ms: int
    status: str
    aligned_lyrics_path: str | None = None


class WhisperXPreloadResponse(BaseModel):
    requested_models: str | None = None
    device: str
    compute_type: str | None = None
    loaded_entries: list[str]
    detail: str


class DemucsJobCreateResponse(BaseModel):
    job_id: str
    status: str
    progress_percent: int
    progress_message: str
    status_url: str
    result_url: str
    cancel_url: str


class DemucsJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "canceled"]
    progress_percent: int
    progress_message: str
    error_detail: str | None = None
    duration_ms: int | None = None
    model: str
    device: str
    output_format: str
    mp3_bitrate: int | None = None
    original_filename: str
    job_kind: Literal["separation", "separation_with_lyrics", "lyrics_alignment"]
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    output_tail: list[str] = []
    aligned_lyrics_path: str | None = None


class DemucsJobArtifactDeleteResponse(BaseModel):
    job_id: str
    status: Literal["completed", "failed", "canceled"]
    detail: str


class DemucsIoUsageResponse(BaseModel):
    io_root: str
    incoming_root: str
    output_root: str
    total_bytes: int
    incoming_bytes: int
    output_bytes: int
    total_files: int
    incoming_files: int
    output_files: int
    active_job_count: int
    running_job_count: int
    terminal_job_count: int
    detail: str


class DemucsIoCleanupResponse(BaseModel):
    io_root: str
    deleted_bytes: int
    deleted_files: int
    deleted_job_count: int
    active_job_count: int
    running_job_count: int
    detail: str


class DemucsMetricsJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running"]
    job_kind: Literal["separation", "separation_with_lyrics", "lyrics_alignment"]
    progress_percent: int
    progress_message: str
    model: str
    device: str
    output_format: str
    mp3_bitrate: int | None = None
    original_filename: str
    created_at: str
    started_at: str | None = None
    cancel_requested: bool
    stdout_tail: list[str] = Field(default_factory=list)


class DemucsMetricsResponse(BaseModel):
    service: str
    snapshot_at: str
    active_job_count: int
    running_job_count: int
    active_job_counts_by_status: dict[str, int]
    active_job_counts_by_kind: dict[str, int]
    free_vram_bytes: int | None = None
    total_vram_bytes: int | None = None
    last_gc_at: str | None = None
    last_gc_mode: Literal["partial", "cuda", "full"] | None = None
    last_gc_detail: str | None = None
    active_jobs: list[DemucsMetricsJobResponse] = Field(default_factory=list)


class DemucsGarbageCollectionResponse(BaseModel):
    requested_mode: Literal["adaptive", "partial", "cuda", "full"]
    executed_mode: Literal["partial", "cuda", "full"]
    triggered_by: Literal["manual", "scheduled", "job_completion", "cancellation"]
    detail: str
    active_job_count: int
    running_job_count: int
    free_vram_bytes: int | None = None
    total_vram_bytes: int | None = None
    python_gc_collected: int
    whisperx_unloaded: dict[str, int] = Field(default_factory=dict)
    cuda_cache_cleared: bool = False
    cuda_ipc_cleared: bool = False
    started_at: str
    finished_at: str
