"""Karaoke service for orchestrating queue and media processing tasks."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from adapters.ffmpeg import FFmpegAdapter
from config import settings
from models import MediaItem, ProcessingTask, ProcessingTaskStatus, QueueItem
from services.demucs_client import DemucsClient
from services.media_naming import build_media_stem
from services.processing_task_service import processing_task_service
from services.queue_service import QueueService
from services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)


class KaraokeService:
    """Service for orchestrating karaoke media generation."""

    def __init__(self):
        self.youtube_service = YouTubeService()
        self.demucs_client = DemucsClient()
        self.queue_service = QueueService()
        self.ffmpeg = FFmpegAdapter()

    @staticmethod
    def _processing_cache_dir() -> Path:
        path = settings.cache_path / "ytdlp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def process_queue_item(self, db: Session, item_id: int):
        """Compatibility wrapper for existing queue processing callers."""
        task = processing_task_service.get_or_create_queue_task(db, item_id)
        await self.process_task(db, task.id)

    async def process_task(self, db: Session, task_id: int):
        """Run one durable processing task."""
        task = processing_task_service.get_task(db, task_id)
        if task is None:
            logger.warning("Processing task not found task_id=%s", task_id)
            return

        await processing_task_service.initialize_live_state(task)
        await processing_task_service.emit_progress(
            task.id,
            progress_percent=0,
            progress_label="Starting task",
            status=task.status,
            stage=task.stage,
        )

        try:
            if task.task_type == "queue_prepare":
                queue_item = db.query(QueueItem).filter(QueueItem.id == task.target_queue_item_id).first()
                if queue_item is None:
                    raise RuntimeError(f"Queue item not found for task {task.id}")
                await self._process_queue_task(db, task, queue_item)
            elif task.task_type == "media_karaoke":
                media_item = db.query(MediaItem).filter(MediaItem.id == task.target_media_item_id).first()
                if media_item is None:
                    raise RuntimeError(f"Media item not found for task {task.id}")
                await self._process_media_task(db, task, media_item)
            else:
                raise RuntimeError(f"Unsupported processing task type: {task.task_type}")
        except Exception as exc:
            logger.exception("Processing task failed task_id=%s", task.id)
            failure_summary = str(exc)
            failure_detail = failure_summary[-400:]
            await processing_task_service.set_status(
                db,
                task.id,
                status=ProcessingTaskStatus.FAILED,
                stage=task.stage or "failed",
                error_summary=failure_summary,
                error_detail=failure_detail,
                progress_label=failure_summary,
            )

    async def _process_queue_task(self, db: Session, task: ProcessingTask, item: QueueItem):
        if item.media is None:
            raise RuntimeError(f"Queue item missing media for id={item.id}")

        existing_media_path = self._existing_media_file(item)
        existing_vocals_path = self._existing_local_file(item.media.vocals_path)
        logger.info(
            "Processing queue task task_id=%s queue_item_id=%s youtube_id=%s karaoke=%s",
            task.id,
            item.id,
            item.media.youtube_id,
            item.requested_karaoke,
        )

        if item.requested_karaoke:
            if existing_media_path and existing_vocals_path:
                await processing_task_service.set_status(
                    db,
                    task.id,
                    status=ProcessingTaskStatus.DONE,
                    stage="ready",
                    progress_label="Reused existing karaoke media",
                    progress_percent=100,
                )
                return
            demucs_health = self.demucs_client.health_check()
            if not demucs_health.healthy:
                raise RuntimeError(
                    f"Demucs unavailable at {demucs_health.api_url}: {demucs_health.detail}"
                )
            video_path, audio_path = await self._prepare_karaoke_inputs(
                db,
                task,
                item.media,
                existing_media_path=existing_media_path,
                use_queue_item=item,
            )
            await self._process_karaoke(db, task, queue_item=item, media_item=item.media, video_path=video_path, audio_path=audio_path)
            return

        if existing_media_path:
            await processing_task_service.set_status(
                db,
                task.id,
                status=ProcessingTaskStatus.DONE,
                stage="ready",
                progress_label="Reused existing media",
                progress_percent=100,
            )
            return

        if not item.media.youtube_id:
            raise RuntimeError("Local queue media already exists but is unavailable on disk")

        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
            progress_label="Downloading media",
            progress_percent=0,
        )
        loop = asyncio.get_running_loop()
        media_stem = self._media_stem_for_media(item.media, fallback=f"queue-{item.id}")
        processing_dir = self._processing_cache_dir()
        video_path = await asyncio.to_thread(
            self._download_video_with_audio_for_task,
            item.media.youtube_id,
            processing_dir,
            loop,
            task.id,
        )
        video_path = await asyncio.to_thread(
            self._rename_downloaded_file,
            video_path,
            media_stem,
            "media",
        )
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.PROCESSING,
            stage="finalize",
            progress_label="Finalizing media",
            progress_percent=95,
        )
        final_media_path = await asyncio.to_thread(
            self._persist_primary_media,
            media_stem,
            video_path,
        )
        self._set_media_item_media_path(db, item.media, final_media_path)
        await processing_task_service.set_status(
            db,
            task.id,
            status=ProcessingTaskStatus.DONE,
            stage="ready",
            progress_label="Ready",
            progress_percent=100,
        )

    async def _process_media_task(self, db: Session, task: ProcessingTask, media_item: MediaItem):
        queue_like_item = QueueItem(id=task.id, media=media_item)  # lightweight carrier for naming helpers
        existing_media_path = self._existing_local_file(media_item.media_path)
        existing_vocals_path = self._existing_local_file(media_item.vocals_path)
        if existing_media_path is None:
            raise RuntimeError("Media item file is missing and cannot be processed")
        if existing_vocals_path is not None:
            await processing_task_service.set_status(
                db,
                task.id,
                status=ProcessingTaskStatus.DONE,
                stage="ready",
                progress_label="Existing karaoke vocals already available",
                progress_percent=100,
            )
            return

        demucs_health = self.demucs_client.health_check()
        if not demucs_health.healthy:
            raise RuntimeError(
                f"Demucs unavailable at {demucs_health.api_url}: {demucs_health.detail}"
            )

        video_path, audio_path = await self._prepare_karaoke_inputs(
            db,
            task,
            media_item,
            existing_media_path=existing_media_path,
            use_queue_item=queue_like_item,
        )
        await self._process_karaoke(
            db,
            task,
            queue_item=None,
            media_item=media_item,
            video_path=video_path,
            audio_path=audio_path,
        )

    async def _prepare_karaoke_inputs(
        self,
        db: Session,
        task: ProcessingTask,
        media_item: MediaItem,
        *,
        existing_media_path: Path | None,
        use_queue_item: QueueItem,
    ) -> tuple[Path, Path]:
        media_stem = self._media_stem_for_media(
            media_item,
            fallback=media_item.youtube_id or f"media-{media_item.id}",
        )
        loop = asyncio.get_running_loop()
        if existing_media_path:
            await processing_task_service.set_stage(
                db,
                task.id,
                status=ProcessingTaskStatus.PROCESSING,
                stage="extract_audio",
                progress_label="Extracting audio",
                progress_percent=10,
            )
            extracted_audio_path = settings.cache_path / "audio" / f"{media_stem}.audio.m4a"
            audio_path = await asyncio.to_thread(
                self.ffmpeg.extract_audio,
                existing_media_path,
                extracted_audio_path,
            )
            await processing_task_service.emit_log(
                task.id,
                message=f"Extracted audio to {audio_path.name}",
                stream="system",
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="extract_audio",
                progress_percent=10,
                progress_label="Extracting audio",
            )
            return existing_media_path, audio_path

        if not media_item.youtube_id:
            raise RuntimeError("Missing YouTube source for karaoke preparation")

        processing_dir = self._processing_cache_dir()
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
            progress_label="Downloading video",
            progress_percent=0,
        )
        video_path = await asyncio.to_thread(
            self._download_video_for_task,
            media_item.youtube_id,
            processing_dir,
            loop,
            task.id,
        )
        video_path = await asyncio.to_thread(
            self._rename_downloaded_file,
            video_path,
            media_stem,
            "media",
        )
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
            progress_label="Downloading audio",
            progress_percent=25,
        )
        audio_path = await asyncio.to_thread(
            self._download_audio_for_task,
            media_item.youtube_id,
            processing_dir,
            loop,
            task.id,
        )
        audio_path = await asyncio.to_thread(
            self._rename_downloaded_file,
            audio_path,
            media_stem,
            "audio",
        )
        return video_path, audio_path

    async def _process_karaoke(
        self,
        db: Session,
        task: ProcessingTask,
        *,
        queue_item: QueueItem | None,
        media_item: MediaItem,
        video_path: Path,
        audio_path: Path,
    ):
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.PROCESSING,
            stage="demucs",
            progress_label="Separating vocals",
            progress_percent=45,
        )
        demucs_response = await self._separate_vocals_with_retry(
            queue_item or QueueItem(id=task.id, media=media_item),
            audio_path,
            task_id=task.id,
        )
        no_vocals_path = Path(demucs_response.no_vocals_path)
        vocals_raw_path = Path(demucs_response.vocals_path) if demucs_response.vocals_path else None
        if vocals_raw_path is None or not vocals_raw_path.exists():
            raise RuntimeError("Demucs response missing vocals output path")
        vocals_sidecar_path = await asyncio.to_thread(
            self._persist_vocals_sidecar,
            queue_item or QueueItem(id=task.id, media=media_item),
            vocals_raw_path,
        )
        self._set_media_item_vocals_path(db, media_item, vocals_sidecar_path)
        await processing_task_service.emit_progress(
            task.id,
            progress_percent=85,
            progress_label="Remuxing karaoke media",
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="finalize",
        )
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.PROCESSING,
            stage="finalize",
            progress_label="Remuxing karaoke media",
            progress_percent=85,
        )
        media_stem = self._media_stem_for_media(
            media_item,
            fallback=media_item.youtube_id or f"media-{media_item.id}",
        )
        output_path = settings.cache_path / "processed" / f"{media_stem}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            self.ffmpeg.combine_audio_video,
            video_path=video_path,
            audio_path=no_vocals_path,
            output_path=output_path,
        )
        final_media_path = await asyncio.to_thread(
            self._persist_primary_media,
            media_stem,
            output_path,
        )
        self._set_media_item_media_path(db, media_item, final_media_path)
        await processing_task_service.set_status(
            db,
            task.id,
            status=ProcessingTaskStatus.DONE,
            stage="ready",
            progress_label="Ready",
            progress_percent=100,
        )

    @staticmethod
    def _existing_media_file(item: QueueItem) -> Path | None:
        """Return a local filesystem path when the queue item already has usable media."""
        if item.media is None or item.media.missing:
            return None
        return KaraokeService._existing_local_file(item.media.media_path)

    @staticmethod
    def _existing_local_file(media_url: str | None) -> Path | None:
        """Map an app media URL to a local file when it exists on disk."""
        if not media_url:
            return None

        media_file = QueueService._media_url_to_file(media_url)
        if media_file is None:
            return None
        return media_file if media_file.exists() else None

    @staticmethod
    def _canonical_vocals_stem(item: QueueItem) -> str:
        """Build a stable basename for persisted vocals sidecars."""
        if item.media:
            return KaraokeService._media_stem_for_media(item.media, fallback=f"queue-{item.id}")
        base = f"queue-{item.id}"
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-")
        return cleaned or f"queue-{item.id}"

    def _persist_vocals_sidecar(self, item: QueueItem, source_path: Path) -> Path:
        """Persist vocals guide track in media storage with canonical *.vocals.<ext> naming."""
        extension = source_path.suffix.lower() or ".wav"
        canonical_name = f"{self._canonical_vocals_stem(item)}.vocals{extension}"
        target_path = settings.media_path / canonical_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() == target_path.resolve():
            return target_path
        shutil.copy2(source_path, target_path)
        return target_path

    def _persist_primary_media(self, media_stem: str, source_path: Path) -> Path:
        """Move the finalized playable media file into durable media storage."""
        target_path = settings.media_path / f"{media_stem}{source_path.suffix.lower()}"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() == target_path.resolve():
            return target_path
        if target_path.exists():
            target_path.unlink()
        shutil.move(str(source_path), str(target_path))
        return target_path

    @staticmethod
    def _media_stem_for_media(media_item: MediaItem, fallback: str) -> str:
        return media_item.file_stem or build_media_stem(
            media_item.title,
            media_item.artist,
            fallback=fallback,
        )

    @staticmethod
    def _rename_downloaded_file(source_path: Path, media_stem: str, media_kind: str) -> Path:
        if media_kind == "audio":
            target_path = source_path.with_name(f"{media_stem}.audio{source_path.suffix}")
        elif media_kind == "media":
            target_path = source_path.with_name(f"{media_stem}{source_path.suffix}")
        else:
            target_path = source_path.with_name(f"{media_stem}{source_path.suffix}")
        if source_path == target_path or not source_path.exists():
            return source_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            logger.warning(
                "Skipping downloaded file rename due to existing target source=%s target=%s",
                source_path,
                target_path,
            )
            return source_path
        shutil.move(str(source_path), str(target_path))
        return target_path

    async def _separate_vocals_with_retry(
        self,
        item: QueueItem,
        audio_path: Path,
        *,
        task_id: int,
    ):
        """Run Demucs separation with one fallback retry for extracted local audio."""
        try:
            return await self.demucs_client.separate_vocals(audio_path)
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code if error.response is not None else None
            can_retry = (
                status_code is not None
                and status_code >= 500
                and audio_path.suffix.lower() == ".m4a"
                and item.media is not None
                and bool(item.media.youtube_id)
            )
            if not can_retry:
                raise

            await processing_task_service.emit_log(
                task_id,
                message="Demucs failed on extracted audio; retrying with fresh yt-dlp audio",
                stream="remote",
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="demucs",
                progress_percent=50,
                progress_label="Retrying Demucs preparation",
            )
            processing_dir = self._processing_cache_dir()
            fallback_audio_path = await asyncio.to_thread(
                self.youtube_service.download_audio,
                item.media.youtube_id,
                processing_dir,
            )
            return await self.demucs_client.separate_vocals(fallback_audio_path)

    @staticmethod
    def _set_media_item_media_path(db: Session, media_item: MediaItem, media_path: Path):
        media_item.media_path = QueueService.build_media_url(media_path)
        media_item.missing = False
        db.commit()

    @staticmethod
    def _set_media_item_vocals_path(db: Session, media_item: MediaItem, vocals_path: Path):
        media_item.vocals_path = QueueService.build_media_url(vocals_path)
        db.commit()

    @staticmethod
    def _progress_callback(
        loop: asyncio.AbstractEventLoop,
        task_id: int,
        start_percent: int,
        end_percent: int,
        label: str,
        *,
        status: str,
        stage: str,
    ):
        last_emit_time = float("-inf")
        last_emit_percent: int | None = None

        def callback(percent: int, raw_line: str):
            nonlocal last_emit_time, last_emit_percent
            mapped = start_percent
            if end_percent > start_percent:
                mapped = start_percent + int((percent / 100.0) * (end_percent - start_percent))
            mapped = max(0, min(100, mapped))
            now = loop.time()
            if (
                last_emit_percent is not None
                and mapped != 100
                and mapped == last_emit_percent
            ):
                return
            if last_emit_percent is not None and mapped != 100 and (now - last_emit_time) < 1.0:
                return
            last_emit_time = now
            last_emit_percent = mapped
            future = asyncio.run_coroutine_threadsafe(
                processing_task_service.emit_progress(
                    task_id,
                    progress_percent=mapped,
                    progress_label=label,
                    status=status,
                    stage=stage,
                ),
                loop,
            )
            future.result(timeout=5)
        return callback

    @staticmethod
    def _log_callback(
        loop: asyncio.AbstractEventLoop,
        task_id: int,
        *,
        status: str,
        stage: str,
    ):
        def callback(stream: str, message: str):
            future = asyncio.run_coroutine_threadsafe(
                processing_task_service.emit_log(
                    task_id,
                    message=message,
                    stream=stream,
                    status=status,
                    stage=stage,
                ),
                loop,
            )
            future.result(timeout=5)
        return callback

    def _download_video_for_task(
        self,
        youtube_id: str,
        output_dir: Path,
        loop: asyncio.AbstractEventLoop,
        task_id: int,
    ) -> Path:
        if isinstance(self.youtube_service, YouTubeService):
            return self.youtube_service.download_video_with_progress(
                youtube_id,
                output_dir,
                progress_callback=self._progress_callback(loop, task_id, 0, 25, "Downloading video", status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
                log_callback=self._log_callback(loop, task_id, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
            )
        return self.youtube_service.download_video(youtube_id, output_dir)

    def _download_audio_for_task(
        self,
        youtube_id: str,
        output_dir: Path,
        loop: asyncio.AbstractEventLoop,
        task_id: int,
    ) -> Path:
        if isinstance(self.youtube_service, YouTubeService):
            return self.youtube_service.download_audio_with_progress(
                youtube_id,
                output_dir,
                progress_callback=self._progress_callback(loop, task_id, 25, 45, "Downloading audio", status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
                log_callback=self._log_callback(loop, task_id, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
            )
        return self.youtube_service.download_audio(youtube_id, output_dir)

    def _download_video_with_audio_for_task(
        self,
        youtube_id: str,
        output_dir: Path,
        loop: asyncio.AbstractEventLoop,
        task_id: int,
    ) -> Path:
        if isinstance(self.youtube_service, YouTubeService):
            return self.youtube_service.download_video_with_audio_progress(
                youtube_id,
                output_dir,
                progress_callback=self._progress_callback(loop, task_id, 0, 90, "Downloading media", status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
                log_callback=self._log_callback(loop, task_id, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
            )
        return self.youtube_service.download_video_with_audio(youtube_id, output_dir)
