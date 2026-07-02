"""Runtime settings service."""
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

from config import EXPLICIT_SETTINGS_FIELDS, find_executable, settings
from models import (
    DemucsGarbageCollectionResponse,
    DemucsHealthResponse,
    ProxyInfoResponse,
    StorageCleanupResponse,
    StorageUsageResponse,
    RuntimeSetting,
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
    WhisperXPreloadResponse,
    YtDlpUpdateResponse,
    YtDlpVersionResponse,
)
from services.demucs_client import DemucsClient
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class RuntimeSettingsService:
    """Manage runtime-editable settings and apply them in-process."""

    ALLOWED_FFMPEG_PRESETS = {
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    }
    ALLOWED_DEMUCS_DEVICES = {"cuda", "cpu"}
    ALLOWED_DEMUCS_OUTPUT_FORMATS = {"wav", "mp3"}
    ALLOWED_PROXY_SCHEMES = {"http", "https", "socks4", "socks4a", "socks5", "socks5h"}
    ALLOWED_YTDLP_VIDEO_RESOLUTIONS = {"default", "360", "480", "720", "1080", "2160"}
    ALLOWED_YTDLP_VIDEO_CODECS = {"", "avc"}
    ALLOWED_FFMPEG_AUDIO_CODECS = {"", "aac"}
    DEMUCS_DIRECT_MEDIA_MAX_MB_RANGE = (0, 5000)
    DEMUCS_POLL_INTERVAL_SECONDS_RANGE = (0.25, 10.0)
    PROXY_INFO_TIMEOUT_SECONDS = 10.0
    YTDLP_PIP_MANAGED_ERROR = "You installed yt-dlp with pip or using the wheel from PyPi"
    PERSISTED_SETTING_FIELDS = (
        "demucs_api_url",
        "demucs_api_key",
        "demucs_model",
        "demucs_device",
        "demucs_output_format",
        "demucs_mp3_bitrate",
        "demucs_direct_media_max_mb",
        "demucs_poll_interval_seconds",
        "whisperx_transcription_model",
        "whisperx_align_language",
        "whisperx_detect_language",
        "whisperx_use_synced_lyrics",
        "whisperx_preload_models",
        "ffmpeg_preset",
        "ffmpeg_crf",
        "ytdlp_path",
        "ytdlp_deno_path",
        "ytdlp_proxy_url",
        "ytdlp_video_resolution",
        "ytdlp_video_codec",
        "concurrent_ytdlp_search_enabled",
        "lyrics_provider_netease_enabled",
        "lyrics_provider_lrclib_enabled",
        "ffmpeg_path",
        "ffmpeg_audio_codec",
        "media_path",
        "cache_path",
        "stage_qr_url",
        "stage_lobby_media_path",
        "stage_vocals_volume_default",
    )
    YTDLP_COMMAND_TIMEOUT_SECONDS = 60

    def get_demucs_health(self) -> DemucsHealthResponse:
        """Return Demucs health for the current configured API URL."""
        return DemucsClient(api_url=settings.demucs_api_url).health_check()

    def preload_whisperx_models(
        self,
        whisperx_preload_models: str | None = None,
    ) -> WhisperXPreloadResponse:
        """Trigger WhisperX model preload/download on the remote Demucs host."""
        return DemucsClient(api_url=settings.demucs_api_url).preload_whisperx_models(
            whisperx_preload_models=whisperx_preload_models,
            device=settings.demucs_device,
        )

    def trigger_demucs_garbage_collection(
        self, mode: str = "adaptive"
    ) -> DemucsGarbageCollectionResponse:
        """Trigger remote Demucs garbage collection."""
        return DemucsClient(api_url=settings.demucs_api_url).trigger_garbage_collection(
            mode=mode
        )

    def get_proxy_info(self, proxy_url: str | None = None) -> ProxyInfoResponse:
        """Resolve public egress details through the configured proxy."""
        proxy = self._validate_proxy_url(
            proxy_url if proxy_url is not None else settings.ytdlp_proxy_url
        )
        if not proxy:
            raise RuntimeError("ytdlp_proxy_url is required to check proxy info")

        try:
            response = httpx.get(
                "https://ipinfo.io/json",
                timeout=self.PROXY_INFO_TIMEOUT_SECONDS,
                proxy=proxy,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Proxy info lookup failed: {error}") from error
        except ValueError as error:
            raise RuntimeError("Proxy info lookup returned invalid JSON") from error

        ip = str(payload.get("ip", "") or "").strip()
        org = str(payload.get("org", "") or "").strip()
        city = str(payload.get("city", "") or "").strip()
        country = str(payload.get("country", "") or "").strip()
        if not ip:
            raise RuntimeError("Proxy info lookup returned no IP address")

        detail = "Proxy info lookup completed"
        return ProxyInfoResponse(
            ip=ip,
            org=org,
            city=city,
            country=country,
            detail=detail,
        )

    def get_storage_usage(self) -> StorageUsageResponse:
        """Estimate current disk usage for the media, cache, and SQLite database."""
        media_bytes = self._path_size_bytes(settings.media_path)
        cache_bytes = self._path_size_bytes(settings.cache_path)
        database_path = self._resolve_sqlite_database_path(settings.database_url)
        database_available = database_path is not None
        database_bytes = self._path_size_bytes(database_path) if database_path is not None else None
        total_bytes = media_bytes + cache_bytes + (database_bytes or 0)

        return StorageUsageResponse(
            media_bytes=media_bytes,
            media_display=self._format_byte_size(media_bytes),
            cache_bytes=cache_bytes,
            cache_display=self._format_byte_size(cache_bytes),
            database_bytes=database_bytes,
            database_display=(
                self._format_byte_size(database_bytes) if database_bytes is not None else None
            ),
            database_available=database_available,
            total_bytes=total_bytes,
            total_display=self._format_byte_size(total_bytes),
        )

    def cleanup_storage(self, db: Session) -> StorageCleanupResponse:
        """Delete cache scratch files and stale database rows."""
        cache_deleted_files, cache_deleted_bytes = self._cleanup_cache_root(settings.cache_path)

        deleted_done_tasks = db.execute(
            text("DELETE FROM processing_tasks WHERE status = 'done'")
        ).rowcount or 0
        deleted_missing_queue_items = db.execute(
            text(
                """
                DELETE FROM queue_items
                WHERE media_id IN (
                    SELECT id FROM media_items WHERE missing = 1
                )
                """
            )
        ).rowcount or 0
        deleted_missing_processing_tasks = db.execute(
            text(
                """
                DELETE FROM processing_tasks
                WHERE target_media_item_id IN (
                    SELECT id FROM media_items WHERE missing = 1
                )
                """
            )
        ).rowcount or 0
        deleted_missing_media_items = db.execute(
            text("DELETE FROM media_items WHERE missing = 1")
        ).rowcount or 0
        db.commit()

        detail = (
            f"Deleted {cache_deleted_files} cache files, "
            f"{deleted_done_tasks} done tasks, and {deleted_missing_media_items} missing media items"
        )
        return StorageCleanupResponse(
            cache_deleted_files=cache_deleted_files,
            cache_deleted_bytes=cache_deleted_bytes,
            db_deleted_done_tasks=deleted_done_tasks,
            db_deleted_missing_queue_items=deleted_missing_queue_items,
            db_deleted_missing_processing_tasks=deleted_missing_processing_tasks,
            db_deleted_missing_media_items=deleted_missing_media_items,
            detail=detail,
        )

    def _build_settings_response(
        self, demucs_health: DemucsHealthResponse | None
    ) -> RuntimeSettingsResponse:
        if demucs_health is None:
            demucs_healthy = False
            demucs_health_detail = "Health check pending"
        else:
            demucs_healthy = demucs_health.healthy
            demucs_health_detail = demucs_health.detail

        return RuntimeSettingsResponse(
            demucs_api_url=settings.demucs_api_url,
            demucs_api_key=settings.demucs_api_key,
            demucs_healthy=demucs_healthy,
            demucs_health_detail=demucs_health_detail,
            demucs_model=settings.demucs_model,
            demucs_device=settings.demucs_device,
            demucs_output_format=settings.demucs_output_format,
            demucs_mp3_bitrate=settings.demucs_mp3_bitrate,
            demucs_direct_media_max_mb=settings.demucs_direct_media_max_mb,
            demucs_poll_interval_seconds=settings.demucs_poll_interval_seconds,
            whisperx_transcription_model=settings.whisperx_transcription_model,
            whisperx_align_language=settings.whisperx_align_language,
            whisperx_detect_language=settings.whisperx_detect_language,
            whisperx_use_synced_lyrics=settings.whisperx_use_synced_lyrics,
            whisperx_preload_models=settings.whisperx_preload_models,
            ffmpeg_preset=settings.ffmpeg_preset,
            ffmpeg_crf=settings.ffmpeg_crf,
            ytdlp_path=settings.ytdlp_path,
            ytdlp_deno_path=settings.ytdlp_deno_path,
            ytdlp_proxy_url=settings.ytdlp_proxy_url,
            ytdlp_video_resolution=settings.ytdlp_video_resolution,
            ytdlp_video_codec=settings.ytdlp_video_codec,
            concurrent_ytdlp_search_enabled=settings.concurrent_ytdlp_search_enabled,
            lyrics_provider_netease_enabled=settings.lyrics_provider_netease_enabled,
            lyrics_provider_lrclib_enabled=settings.lyrics_provider_lrclib_enabled,
            ffmpeg_path=settings.ffmpeg_path,
            ffmpeg_audio_codec=settings.ffmpeg_audio_codec,
            media_path=str(settings.media_path),
            cache_path=str(settings.cache_path),
            stage_qr_url=settings.stage_qr_url,
            stage_lobby_media_path=settings.stage_lobby_media_path,
            stage_vocals_volume_default=settings.stage_vocals_volume_default,
        )

    def get_settings(self) -> RuntimeSettingsResponse:
        """Return current runtime settings snapshot without blocking network calls."""
        return self._build_settings_response(demucs_health=None)

    def load_persisted_settings(self, db: Session) -> list[str]:
        """Load persisted runtime settings into the in-memory settings object."""
        persisted_rows = db.query(RuntimeSetting).all()
        persisted_values = {row.key: row.value for row in persisted_rows}
        applied_fields: list[str] = []

        for field_name in self.PERSISTED_SETTING_FIELDS:
            if field_name in EXPLICIT_SETTINGS_FIELDS:
                continue
            raw_value = persisted_values.get(field_name)
            if raw_value is None:
                continue
            self._apply_persisted_setting(field_name, raw_value)
            applied_fields.append(field_name)

        if applied_fields:
            settings.ensure_paths()

        return applied_fields

    def update_settings(
        self, payload: RuntimeSettingsUpdateRequest, db: Session | None = None
    ) -> RuntimeSettingsResponse:
        """Apply validated runtime setting updates."""
        updated_fields: list[str] = []
        snapshot: dict[str, object] = {}

        if payload.demucs_api_url is not None:
            value = payload.demucs_api_url.strip()
            if not value:
                raise ValueError("demucs_api_url cannot be empty")
            snapshot.setdefault("demucs_api_url", settings.demucs_api_url)
            settings.demucs_api_url = value
            updated_fields.append("demucs_api_url")

        if payload.demucs_api_key is not None:
            snapshot.setdefault("demucs_api_key", settings.demucs_api_key)
            settings.demucs_api_key = payload.demucs_api_key.strip()
            updated_fields.append("demucs_api_key")

        if payload.demucs_model is not None:
            model = payload.demucs_model.strip()
            if not model:
                raise ValueError("demucs_model cannot be empty")
            snapshot.setdefault("demucs_model", settings.demucs_model)
            settings.demucs_model = model
            updated_fields.append("demucs_model")

        if payload.demucs_device is not None:
            device = payload.demucs_device.strip().lower()
            if device not in self.ALLOWED_DEMUCS_DEVICES:
                raise ValueError(
                    "demucs_device must be one of: "
                    + ", ".join(sorted(self.ALLOWED_DEMUCS_DEVICES))
                )
            snapshot.setdefault("demucs_device", settings.demucs_device)
            settings.demucs_device = device
            updated_fields.append("demucs_device")

        if payload.demucs_output_format is not None:
            output_format = payload.demucs_output_format.strip().lower()
            if output_format not in self.ALLOWED_DEMUCS_OUTPUT_FORMATS:
                raise ValueError(
                    "demucs_output_format must be one of: "
                    + ", ".join(sorted(self.ALLOWED_DEMUCS_OUTPUT_FORMATS))
                )
            snapshot.setdefault("demucs_output_format", settings.demucs_output_format)
            settings.demucs_output_format = output_format
            updated_fields.append("demucs_output_format")

        if payload.demucs_mp3_bitrate is not None:
            bitrate = payload.demucs_mp3_bitrate
            if bitrate < 64 or bitrate > 320:
                raise ValueError("demucs_mp3_bitrate must be between 64 and 320")
            snapshot.setdefault("demucs_mp3_bitrate", settings.demucs_mp3_bitrate)
            settings.demucs_mp3_bitrate = bitrate
            updated_fields.append("demucs_mp3_bitrate")

        if payload.demucs_direct_media_max_mb is not None:
            max_mb = payload.demucs_direct_media_max_mb
            if not self._is_valid_demucs_direct_media_max_mb(max_mb):
                min_mb, max_mb_allowed = self.DEMUCS_DIRECT_MEDIA_MAX_MB_RANGE
                raise ValueError(
                    "demucs_direct_media_max_mb must be between "
                    f"{min_mb} and {max_mb_allowed}"
                )
            snapshot.setdefault(
                "demucs_direct_media_max_mb", settings.demucs_direct_media_max_mb
            )
            settings.demucs_direct_media_max_mb = max_mb
            updated_fields.append("demucs_direct_media_max_mb")

        if payload.demucs_poll_interval_seconds is not None:
            poll_interval = float(payload.demucs_poll_interval_seconds)
            if not self._is_valid_demucs_poll_interval_seconds(poll_interval):
                min_seconds, max_seconds = self.DEMUCS_POLL_INTERVAL_SECONDS_RANGE
                raise ValueError(
                    "demucs_poll_interval_seconds must be between "
                    f"{min_seconds} and {max_seconds}"
                )
            snapshot.setdefault(
                "demucs_poll_interval_seconds", settings.demucs_poll_interval_seconds
            )
            settings.demucs_poll_interval_seconds = poll_interval
            updated_fields.append("demucs_poll_interval_seconds")

        if payload.whisperx_transcription_model is not None:
            transcription_model = payload.whisperx_transcription_model.strip()
            if not transcription_model:
                raise ValueError("whisperx_transcription_model cannot be empty")
            snapshot.setdefault(
                "whisperx_transcription_model", settings.whisperx_transcription_model
            )
            settings.whisperx_transcription_model = transcription_model
            updated_fields.append("whisperx_transcription_model")

        if payload.whisperx_align_language is not None:
            align_language = payload.whisperx_align_language.strip().lower()
            snapshot.setdefault("whisperx_align_language", settings.whisperx_align_language)
            settings.whisperx_align_language = align_language or ""
            updated_fields.append("whisperx_align_language")

        if payload.whisperx_detect_language is not None:
            snapshot.setdefault("whisperx_detect_language", settings.whisperx_detect_language)
            settings.whisperx_detect_language = payload.whisperx_detect_language
            updated_fields.append("whisperx_detect_language")

        if payload.whisperx_use_synced_lyrics is not None:
            snapshot.setdefault(
                "whisperx_use_synced_lyrics", settings.whisperx_use_synced_lyrics
            )
            settings.whisperx_use_synced_lyrics = payload.whisperx_use_synced_lyrics
            updated_fields.append("whisperx_use_synced_lyrics")

        if payload.whisperx_preload_models is not None:
            preload_models = payload.whisperx_preload_models.strip()
            snapshot.setdefault("whisperx_preload_models", settings.whisperx_preload_models)
            settings.whisperx_preload_models = preload_models
            updated_fields.append("whisperx_preload_models")

        if payload.ffmpeg_preset is not None:
            preset = payload.ffmpeg_preset.strip().lower()
            if preset not in self.ALLOWED_FFMPEG_PRESETS:
                raise ValueError(
                    "ffmpeg_preset must be one of: "
                    + ", ".join(sorted(self.ALLOWED_FFMPEG_PRESETS))
                )
            snapshot.setdefault("ffmpeg_preset", settings.ffmpeg_preset)
            settings.ffmpeg_preset = preset
            updated_fields.append("ffmpeg_preset")

        if payload.ffmpeg_crf is not None:
            crf = payload.ffmpeg_crf
            if crf < 0 or crf > 51:
                raise ValueError("ffmpeg_crf must be between 0 and 51")
            snapshot.setdefault("ffmpeg_crf", settings.ffmpeg_crf)
            settings.ffmpeg_crf = crf
            updated_fields.append("ffmpeg_crf")

        if payload.ytdlp_path is not None:
            ytdlp_input = payload.ytdlp_path.strip()
            if not ytdlp_input:
                raise ValueError("ytdlp_path cannot be empty")
            snapshot.setdefault("ytdlp_path", settings.ytdlp_path)
            settings.ytdlp_path = self._resolve_executable_path(ytdlp_input)
            updated_fields.append("ytdlp_path")

        if payload.ytdlp_deno_path is not None:
            snapshot.setdefault("ytdlp_deno_path", settings.ytdlp_deno_path)
            settings.ytdlp_deno_path = payload.ytdlp_deno_path.strip()
            updated_fields.append("ytdlp_deno_path")

        if payload.ytdlp_proxy_url is not None:
            proxy = self._validate_proxy_url(payload.ytdlp_proxy_url)
            snapshot.setdefault("ytdlp_proxy_url", settings.ytdlp_proxy_url)
            settings.ytdlp_proxy_url = proxy
            updated_fields.append("ytdlp_proxy_url")

        if payload.ytdlp_video_resolution is not None:
            resolution = payload.ytdlp_video_resolution.strip().lower()
            if resolution not in self.ALLOWED_YTDLP_VIDEO_RESOLUTIONS:
                raise ValueError(
                    "ytdlp_video_resolution must be one of: "
                    + ", ".join(sorted(self.ALLOWED_YTDLP_VIDEO_RESOLUTIONS))
                )
            snapshot.setdefault("ytdlp_video_resolution", settings.ytdlp_video_resolution)
            settings.ytdlp_video_resolution = resolution
            updated_fields.append("ytdlp_video_resolution")

        if payload.ytdlp_video_codec is not None:
            video_codec = payload.ytdlp_video_codec.strip().lower()
            if video_codec not in self.ALLOWED_YTDLP_VIDEO_CODECS:
                raise ValueError(
                    "ytdlp_video_codec must be blank or one of: "
                    + ", ".join(sorted(value for value in self.ALLOWED_YTDLP_VIDEO_CODECS if value))
                )
            snapshot.setdefault("ytdlp_video_codec", settings.ytdlp_video_codec)
            settings.ytdlp_video_codec = video_codec
            updated_fields.append("ytdlp_video_codec")

        if payload.concurrent_ytdlp_search_enabled is not None:
            snapshot.setdefault(
                "concurrent_ytdlp_search_enabled", settings.concurrent_ytdlp_search_enabled
            )
            settings.concurrent_ytdlp_search_enabled = payload.concurrent_ytdlp_search_enabled
            updated_fields.append("concurrent_ytdlp_search_enabled")

        if payload.lyrics_provider_netease_enabled is not None:
            snapshot.setdefault(
                "lyrics_provider_netease_enabled", settings.lyrics_provider_netease_enabled
            )
            settings.lyrics_provider_netease_enabled = payload.lyrics_provider_netease_enabled
            updated_fields.append("lyrics_provider_netease_enabled")

        if payload.lyrics_provider_lrclib_enabled is not None:
            snapshot.setdefault(
                "lyrics_provider_lrclib_enabled", settings.lyrics_provider_lrclib_enabled
            )
            settings.lyrics_provider_lrclib_enabled = payload.lyrics_provider_lrclib_enabled
            updated_fields.append("lyrics_provider_lrclib_enabled")

        if payload.ffmpeg_path is not None:
            ffmpeg_input = payload.ffmpeg_path.strip()
            if not ffmpeg_input:
                raise ValueError("ffmpeg_path cannot be empty")
            snapshot.setdefault("ffmpeg_path", settings.ffmpeg_path)
            settings.ffmpeg_path = self._resolve_executable_path(ffmpeg_input)
            updated_fields.append("ffmpeg_path")

        if payload.ffmpeg_audio_codec is not None:
            audio_codec = payload.ffmpeg_audio_codec.strip().lower()
            if audio_codec not in self.ALLOWED_FFMPEG_AUDIO_CODECS:
                raise ValueError(
                    "ffmpeg_audio_codec must be blank or one of: "
                    + ", ".join(sorted(value for value in self.ALLOWED_FFMPEG_AUDIO_CODECS if value))
                )
            snapshot.setdefault("ffmpeg_audio_codec", settings.ffmpeg_audio_codec)
            settings.ffmpeg_audio_codec = audio_codec
            updated_fields.append("ffmpeg_audio_codec")

        if payload.media_path is not None:
            media_path_input = payload.media_path.strip()
            if not media_path_input:
                raise ValueError("media_path cannot be empty")
            snapshot.setdefault("media_path", settings.media_path)
            settings.media_path = Path(media_path_input)
            updated_fields.append("media_path")

        if payload.cache_path is not None:
            cache_path_input = payload.cache_path.strip()
            if not cache_path_input:
                raise ValueError("cache_path cannot be empty")
            snapshot.setdefault("cache_path", settings.cache_path)
            settings.cache_path = Path(cache_path_input)
            updated_fields.append("cache_path")

        if payload.stage_qr_url is not None:
            snapshot.setdefault("stage_qr_url", settings.stage_qr_url)
            settings.stage_qr_url = payload.stage_qr_url.strip()
            updated_fields.append("stage_qr_url")

        if payload.stage_lobby_media_path is not None:
            snapshot.setdefault("stage_lobby_media_path", settings.stage_lobby_media_path)
            settings.stage_lobby_media_path = payload.stage_lobby_media_path.strip()
            updated_fields.append("stage_lobby_media_path")

        if payload.stage_vocals_volume_default is not None:
            default_volume = float(payload.stage_vocals_volume_default)
            if default_volume < 0.0 or default_volume > 1.0:
                raise ValueError("stage_vocals_volume_default must be between 0.0 and 1.0")
            snapshot.setdefault(
                "stage_vocals_volume_default", settings.stage_vocals_volume_default
            )
            settings.stage_vocals_volume_default = default_volume
            updated_fields.append("stage_vocals_volume_default")

        try:
            settings.ensure_paths()
            if db is not None and updated_fields:
                self._persist_settings(db, updated_fields)
        except Exception:
            for field_name, previous_value in snapshot.items():
                setattr(settings, field_name, previous_value)
            settings.ensure_paths()
            raise

        demucs_health = self.get_demucs_health()
        return self._build_settings_response(demucs_health=demucs_health)

    def _apply_persisted_setting(self, field_name: str, raw_value: str) -> None:
        """Apply a single persisted setting value to the in-memory settings object."""
        if field_name == "demucs_api_url":
            settings.demucs_api_url = raw_value
        elif field_name == "demucs_api_key":
            settings.demucs_api_key = raw_value.strip()
        elif field_name == "demucs_model":
            settings.demucs_model = raw_value
        elif field_name == "demucs_device":
            device = raw_value.strip().lower()
            if device not in self.ALLOWED_DEMUCS_DEVICES:
                raise ValueError(f"Invalid persisted demucs_device: {raw_value}")
            settings.demucs_device = device
        elif field_name == "demucs_output_format":
            output_format = raw_value.strip().lower()
            if output_format not in self.ALLOWED_DEMUCS_OUTPUT_FORMATS:
                raise ValueError(f"Invalid persisted demucs_output_format: {raw_value}")
            settings.demucs_output_format = output_format
        elif field_name == "demucs_mp3_bitrate":
            settings.demucs_mp3_bitrate = int(raw_value)
        elif field_name == "demucs_direct_media_max_mb":
            max_mb = int(raw_value)
            if not self._is_valid_demucs_direct_media_max_mb(max_mb):
                raise ValueError(f"Invalid persisted demucs_direct_media_max_mb: {raw_value}")
            settings.demucs_direct_media_max_mb = max_mb
        elif field_name == "demucs_poll_interval_seconds":
            poll_interval = float(raw_value)
            if not self._is_valid_demucs_poll_interval_seconds(poll_interval):
                raise ValueError(f"Invalid persisted demucs_poll_interval_seconds: {raw_value}")
            settings.demucs_poll_interval_seconds = poll_interval
        elif field_name == "whisperx_transcription_model":
            transcription_model = raw_value.strip()
            if not transcription_model:
                raise ValueError("Invalid persisted whisperx_transcription_model: empty value")
            settings.whisperx_transcription_model = transcription_model
        elif field_name == "whisperx_align_language":
            settings.whisperx_align_language = raw_value.strip().lower()
        elif field_name == "whisperx_detect_language":
            settings.whisperx_detect_language = raw_value.lower() in {"1", "true", "yes", "on"}
        elif field_name == "whisperx_use_synced_lyrics":
            settings.whisperx_use_synced_lyrics = raw_value.lower() in {"1", "true", "yes", "on"}
        elif field_name == "whisperx_preload_models":
            settings.whisperx_preload_models = raw_value.strip()
        elif field_name == "ffmpeg_preset":
            preset = raw_value.strip().lower()
            if preset not in self.ALLOWED_FFMPEG_PRESETS:
                raise ValueError(f"Invalid persisted ffmpeg_preset: {raw_value}")
            settings.ffmpeg_preset = preset
        elif field_name == "ffmpeg_crf":
            settings.ffmpeg_crf = int(raw_value)
        elif field_name == "ytdlp_path":
            settings.ytdlp_path = self._resolve_executable_path(raw_value.strip())
        elif field_name == "ytdlp_deno_path":
            settings.ytdlp_deno_path = raw_value.strip()
        elif field_name == "ytdlp_proxy_url":
            settings.ytdlp_proxy_url = raw_value
        elif field_name == "ytdlp_video_resolution":
            resolution = raw_value.strip().lower()
            if resolution not in self.ALLOWED_YTDLP_VIDEO_RESOLUTIONS:
                raise ValueError(f"Invalid persisted ytdlp_video_resolution: {raw_value}")
            settings.ytdlp_video_resolution = resolution
        elif field_name == "ytdlp_video_codec":
            video_codec = raw_value.strip().lower()
            if video_codec not in self.ALLOWED_YTDLP_VIDEO_CODECS:
                raise ValueError(f"Invalid persisted ytdlp_video_codec: {raw_value}")
            settings.ytdlp_video_codec = video_codec
        elif field_name == "concurrent_ytdlp_search_enabled":
            settings.concurrent_ytdlp_search_enabled = raw_value.lower() in {"1", "true", "yes", "on"}
        elif field_name == "lyrics_provider_netease_enabled":
            settings.lyrics_provider_netease_enabled = raw_value.lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        elif field_name == "lyrics_provider_lrclib_enabled":
            settings.lyrics_provider_lrclib_enabled = raw_value.lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        elif field_name == "ffmpeg_path":
            settings.ffmpeg_path = self._resolve_executable_path(raw_value.strip())
        elif field_name == "ffmpeg_audio_codec":
            audio_codec = raw_value.strip().lower()
            if audio_codec not in self.ALLOWED_FFMPEG_AUDIO_CODECS:
                raise ValueError(f"Invalid persisted ffmpeg_audio_codec: {raw_value}")
            settings.ffmpeg_audio_codec = audio_codec
        elif field_name == "media_path":
            settings.media_path = Path(raw_value)
        elif field_name == "cache_path":
            settings.cache_path = Path(raw_value)
        elif field_name == "stage_qr_url":
            settings.stage_qr_url = raw_value
        elif field_name == "stage_lobby_media_path":
            settings.stage_lobby_media_path = raw_value
        elif field_name == "stage_vocals_volume_default":
            volume = float(raw_value)
            if volume < 0.0 or volume > 1.0:
                raise ValueError(
                    f"Invalid persisted stage_vocals_volume_default: {raw_value}"
                )
            settings.stage_vocals_volume_default = volume
        else:
            raise ValueError(f"Unknown persisted runtime setting: {field_name}")

    def _serialize_persisted_setting(self, field_name: str) -> str:
        """Serialize the current in-memory setting value for persistence."""
        value = getattr(settings, field_name)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _persist_settings(self, db: Session, field_names: list[str]) -> None:
        """Upsert the selected runtime settings into the database."""
        for field_name in field_names:
            persisted_value = self._serialize_persisted_setting(field_name)
            row = db.get(RuntimeSetting, field_name)
            if row is None:
                row = RuntimeSetting(key=field_name, value=persisted_value)
                db.add(row)
            else:
                row.value = persisted_value
        db.commit()

    @staticmethod
    def _resolve_executable_path(value: str) -> str:
        """Resolve executable name/path similar to startup behavior."""
        candidate = Path(value)
        if candidate.exists():
            return str(candidate)
        return find_executable(value.split("/")[-1])

    @staticmethod
    def _path_size_bytes(path: Path | None) -> int:
        """Return the total size of a file or directory tree in bytes."""
        if path is None:
            return 0
        try:
            if not path.exists():
                return 0
            if path.is_symlink():
                return 0
            if path.is_file():
                return path.stat().st_size
        except OSError:
            return 0

        total = 0
        stack = [path]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(Path(entry.path))
                                continue
                            if entry.is_file(follow_symlinks=False):
                                total += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            logger.warning(
                                "Failed to inspect storage entry path=%s",
                                entry.path,
                            )
            except OSError:
                logger.warning("Failed to scan storage path=%s", current)
        return total

    @staticmethod
    def _cleanup_cache_root(cache_root: Path) -> tuple[int, int]:
        """Delete cache files while preserving the media-thumbnails directory."""
        if not cache_root.exists():
            return 0, 0

        deleted_files = 0
        deleted_bytes = 0
        for child in cache_root.iterdir():
            if child.name == "media-thumbnails":
                continue
            child_files, child_bytes = RuntimeSettingsService._delete_path_tree(child)
            deleted_files += child_files
            deleted_bytes += child_bytes
        return deleted_files, deleted_bytes

    @staticmethod
    def _delete_path_tree(path: Path) -> tuple[int, int]:
        """Delete a file tree and return deleted file count and bytes."""
        if not path.exists():
            return 0, 0

        if path.is_symlink() or path.is_file():
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            try:
                path.unlink()
            except OSError:
                logger.warning("Failed to delete cache file path=%s", path)
                return 0, 0
            return 1, size

        if not path.is_dir():
            return 0, 0

        deleted_files = 0
        deleted_bytes = 0
        try:
            entries = list(path.iterdir())
        except OSError:
            logger.warning("Failed to list cache directory path=%s", path)
            return 0, 0

        for child in entries:
            child_files, child_bytes = RuntimeSettingsService._delete_path_tree(child)
            deleted_files += child_files
            deleted_bytes += child_bytes

        try:
            path.rmdir()
        except OSError:
            logger.warning("Failed to remove cache directory path=%s", path)
        return deleted_files, deleted_bytes

    @staticmethod
    def _resolve_sqlite_database_path(database_url: str) -> Path | None:
        """Resolve a file-backed SQLite database path when one exists."""
        try:
            parsed = make_url(database_url)
        except Exception as error:
            raise ValueError(f"Invalid database_url: {database_url}") from error

        if parsed.get_backend_name() != "sqlite":
            return None

        database = (parsed.database or "").strip()
        if not database or database == ":memory:":
            return None

        if parsed.query.get("mode") == "memory":
            return None

        if database.startswith("file:"):
            return None

        path = Path(database)
        if not path.is_absolute():
            path = path.resolve()
        return path

    @staticmethod
    def _format_byte_size(size_bytes: int) -> str:
        """Format a byte count for operator display."""
        units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
        value = float(max(0, size_bytes))
        unit_index = 0
        while value >= 1024.0 and unit_index < len(units) - 1:
            value /= 1024.0
            unit_index += 1
        if unit_index == 0:
            return f"{int(value)} {units[unit_index]}"
        return f"{value:.1f} {units[unit_index]}"

    def _validate_proxy_url(self, value: str) -> str:
        """Validate a proxy URL or normalize it to an empty string."""
        proxy = value.strip()
        if proxy:
            parsed = urlparse(proxy)
            if (
                not parsed.scheme
                or parsed.scheme.lower() not in self.ALLOWED_PROXY_SCHEMES
                or not parsed.netloc
            ):
                raise ValueError(
                    "ytdlp_proxy_url must be empty or a valid proxy URL with scheme "
                    + ", ".join(sorted(self.ALLOWED_PROXY_SCHEMES))
                )
        return proxy

    @classmethod
    def _is_valid_demucs_direct_media_max_mb(cls, value: int) -> bool:
        min_mb, max_mb = cls.DEMUCS_DIRECT_MEDIA_MAX_MB_RANGE
        return min_mb <= value <= max_mb

    @classmethod
    def _is_valid_demucs_poll_interval_seconds(cls, value: float) -> bool:
        min_seconds, max_seconds = cls.DEMUCS_POLL_INTERVAL_SECONDS_RANGE
        return min_seconds <= value <= max_seconds

    def get_ytdlp_version(self) -> YtDlpVersionResponse:
        """Return currently active yt-dlp version."""
        cmd = [settings.ytdlp_path, "--version"]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.YTDLP_COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as error:
            raise RuntimeError(f"yt-dlp binary not found: {settings.ytdlp_path}") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("yt-dlp version check timed out") from error
        except subprocess.CalledProcessError as error:
            stderr = (error.stderr or "").strip()
            raise RuntimeError(f"yt-dlp version check failed: {stderr or 'unknown error'}") from error

        version = (result.stdout or "").strip()
        if not version:
            raise RuntimeError("yt-dlp version check returned empty output")
        return YtDlpVersionResponse(version=version, binary_path=settings.ytdlp_path)

    def _resolve_ytdlp_python_executable(self) -> str:
        """Return the Python executable that owns the configured yt-dlp install."""
        ytdlp_path = Path(settings.ytdlp_path)
        try:
            with ytdlp_path.open("rb") as handle:
                shebang = handle.readline(256).decode("utf-8", errors="ignore").strip()
        except OSError:
            return sys.executable

        if shebang.startswith("#!"):
            interpreter = shebang[2:].strip().split(" ", 1)[0]
            if interpreter:
                return interpreter
        return sys.executable

    def _update_ytdlp_via_package_manager(self) -> subprocess.CompletedProcess[str]:
        """Update yt-dlp with the package manager used by the active install."""
        python_executable = self._resolve_ytdlp_python_executable()
        if shutil.which("uv"):
            cmd = ["uv", "pip", "install", "--upgrade", "yt-dlp", "--python", python_executable]
        else:
            cmd = [python_executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]

        try:
            return subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.YTDLP_COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as error:
            raise RuntimeError("yt-dlp package-manager update tool not found") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("yt-dlp package-manager update timed out") from error
        except subprocess.CalledProcessError as error:
            stderr = (error.stderr or "").strip()
            raise RuntimeError(
                f"yt-dlp package-manager update failed: {stderr or 'unknown error'}"
            ) from error

    def update_ytdlp(self) -> YtDlpUpdateResponse:
        """Run `yt-dlp -U` and return update summary."""
        before = self.get_ytdlp_version()
        cmd = [settings.ytdlp_path, "-U"]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.YTDLP_COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as error:
            raise RuntimeError(f"yt-dlp binary not found: {settings.ytdlp_path}") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("yt-dlp update timed out") from error
        except subprocess.CalledProcessError as error:
            stderr = (error.stderr or "").strip()
            if self.YTDLP_PIP_MANAGED_ERROR in stderr:
                logger.info(
                    "yt-dlp update fell back to package-manager install binary=%s python=%s",
                    settings.ytdlp_path,
                    self._resolve_ytdlp_python_executable(),
                )
                result = self._update_ytdlp_via_package_manager()
            else:
                raise RuntimeError(f"yt-dlp update failed: {stderr or 'unknown error'}") from error

        after = self.get_ytdlp_version()
        updated = before.version != after.version
        if updated:
            detail = ((result.stdout or "").strip() or "yt-dlp update command completed")[:500]
        else:
            detail = f"yt-dlp is up to date ({after.version})"
        return YtDlpUpdateResponse(
            before_version=before.version,
            after_version=after.version,
            updated=updated,
            detail=detail,
        )
