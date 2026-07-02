"""Karaoke service for orchestrating queue and media processing tasks."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
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
from services.vocal_sync_service import VocalSyncService
from services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)

_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"}


class KaraokeService:
    """Service for orchestrating karaoke media generation."""

    def __init__(self):
        self.youtube_service = YouTubeService()
        self.demucs_client = DemucsClient()
        self.queue_service = QueueService()
        self.ffmpeg = FFmpegAdapter()
        self.vocal_sync_service = VocalSyncService()

    @staticmethod
    def _task_cache_dir(category: str, task_id: int) -> Path:
        path = settings.cache_path / category / str(task_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def process_queue_item(self, db: Session, item_id: int):
        """Compatibility wrapper for existing queue processing callers."""
        task = processing_task_service.get_or_create_queue_task(db, item_id)
        await self.process_task(db, task.id)

    async def process_task(
        self,
        db: Session,
        task_id: int,
        *,
        cancel_event: threading.Event | None = None,
    ):
        """Run one durable processing task."""
        task = processing_task_service.get_task(db, task_id)
        if task is None:
            logger.warning("Processing task not found task_id=%s", task_id)
            return

        await processing_task_service.initialize_live_state(task)
        try:
            await self._raise_if_canceled(cancel_event, task.id)
            await processing_task_service.emit_progress(
                task.id,
                queue_item_id=task.target_queue_item_id,
                progress_percent=0,
                progress_label="Starting task",
                progress_label_key="task.starting",
                status=task.status,
                stage=task.stage,
            )
            if task.task_type == "queue_prepare":
                queue_item = db.query(QueueItem).filter(QueueItem.id == task.target_queue_item_id).first()
                if queue_item is None:
                    raise RuntimeError(f"Queue item not found for task {task.id}")
                await self._process_queue_task(db, task, queue_item, cancel_event=cancel_event)
            elif task.task_type in {"media_karaoke", "media_karaoke_align"}:
                media_item = db.query(MediaItem).filter(MediaItem.id == task.target_media_item_id).first()
                if media_item is None:
                    raise RuntimeError(f"Media item not found for task {task.id}")
                await self._process_media_task(db, task, media_item, cancel_event=cancel_event)
            elif task.task_type == "media_lyrics_align":
                media_item = db.query(MediaItem).filter(MediaItem.id == task.target_media_item_id).first()
                if media_item is None:
                    raise RuntimeError(f"Media item not found for task {task.id}")
                await self._process_media_lyrics_align_task(db, task, media_item, cancel_event=cancel_event)
            elif task.task_type in {"media_vocal_sync_prepare_youtube", "media_vocal_sync_prepare_upload"}:
                media_item = db.query(MediaItem).filter(MediaItem.id == task.target_media_item_id).first()
                if media_item is None:
                    raise RuntimeError(f"Media item not found for task {task.id}")
                if task.task_type == "media_vocal_sync_prepare_youtube":
                    await self._process_media_vocal_sync_prepare_task(
                        db,
                        task,
                        media_item,
                        cancel_event=cancel_event,
                    )
                else:
                    await self._process_media_vocal_sync_prepare_upload_task(
                        db,
                        task,
                        media_item,
                        cancel_event=cancel_event,
                    )
            else:
                raise RuntimeError(f"Unsupported processing task type: {task.task_type}")
            db.refresh(task)
            if task.status == ProcessingTaskStatus.DONE.value:
                self.cleanup_successful_task(task)
        except asyncio.CancelledError:
            logger.info("Processing task canceled task_id=%s", task.id)
            await self._finalize_cancellation(db, task)
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

    @staticmethod
    async def _raise_if_canceled(cancel_event: threading.Event | None, task_id: int):
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()
        await asyncio.sleep(0)
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()

    async def _process_queue_task(
        self,
        db: Session,
        task: ProcessingTask,
        item: QueueItem,
        *,
        cancel_event: threading.Event | None = None,
    ):
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
            await self._raise_if_canceled(cancel_event, task.id)
            if existing_media_path and existing_vocals_path:
                await processing_task_service.set_status(
                    db,
                    task.id,
                    status=ProcessingTaskStatus.DONE,
                    stage="ready",
                    progress_label="Reused existing karaoke media",
                    progress_label_key="task.reused_existing_karaoke_media",
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
                queue_item_id=item.id,
                cancel_event=cancel_event,
            )
            await self._process_karaoke(
                db,
                task,
                queue_item=item,
                media_item=item.media,
                video_path=video_path,
                audio_path=audio_path,
                align_lyrics=bool(item.requested_lyrics_alignment),
                cancel_event=cancel_event,
            )
            return

        if existing_media_path:
            await self._raise_if_canceled(cancel_event, task.id)
            await processing_task_service.set_status(
                db,
                task.id,
                status=ProcessingTaskStatus.DONE,
                stage="ready",
                progress_label="Reused existing media",
                progress_label_key="task.reused_existing_media",
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
            progress_label_key="task.downloading_media",
            progress_percent=0,
            progress_step_index=1,
            progress_step_total=2,
        )
        loop = asyncio.get_running_loop()
        media_stem = self._media_stem_for_media(item.media, fallback=f"queue-{item.id}")
        processing_dir = self._task_cache_dir("ytdlp", task.id)
        video_path = await asyncio.to_thread(
            lambda: self._download_video_with_audio_for_task(
                item.media.youtube_id,
                processing_dir,
                loop,
                task.id,
                item.id,
                step_index=1,
                step_total=2,
                cancel_event=cancel_event,
            )
        )
        await self._raise_if_canceled(cancel_event, task.id)
        video_path = await asyncio.to_thread(
            self._rename_downloaded_file,
            video_path,
            media_stem,
            "media",
        )
        await self._raise_if_canceled(cancel_event, task.id)
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.PROCESSING,
            stage="finalize",
            progress_label="Finalizing media",
            progress_label_key="task.finalizing_media",
            progress_percent=0,
            progress_step_index=2,
            progress_step_total=2,
        )
        final_media_path = await asyncio.to_thread(
            self._persist_primary_media,
            media_stem,
            video_path,
        )
        await self._raise_if_canceled(cancel_event, task.id)
        self._set_media_item_media_path(db, item.media, final_media_path)
        await processing_task_service.set_status(
            db,
            task.id,
            status=ProcessingTaskStatus.DONE,
            stage="ready",
            progress_label="Ready",
            progress_label_key="task.ready",
            progress_percent=100,
        )

    async def _process_media_task(
        self,
        db: Session,
        task: ProcessingTask,
        media_item: MediaItem,
        *,
        cancel_event: threading.Event | None = None,
    ):
        existing_media_path = self._existing_local_file(media_item.media_path)
        existing_vocals_path = self._existing_local_file(media_item.vocals_path)
        align_lyrics = task.task_type == "media_karaoke_align"
        if existing_media_path is None:
            raise RuntimeError("Media item file is missing and cannot be processed")
        if existing_vocals_path is not None:
            if align_lyrics:
                await self._process_media_lyrics_align_task(db, task, media_item, cancel_event=cancel_event)
                return
            await self._raise_if_canceled(cancel_event, task.id)
            await processing_task_service.set_status(
                db,
                task.id,
                status=ProcessingTaskStatus.DONE,
                stage="ready",
                progress_label="Existing karaoke vocals already available",
                progress_label_key="task.reused_existing_karaoke_media",
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
            cancel_event=cancel_event,
        )
        await self._process_karaoke(
            db,
            task,
            queue_item=None,
            media_item=media_item,
            video_path=video_path,
            audio_path=audio_path,
            align_lyrics=align_lyrics,
            whisperx_align_language_override=task.whisperx_align_language_override,
            process_lyrics_lines=task.process_lyrics_lines,
            max_line_length=task.max_line_length,
            max_line_length_cjk=task.max_line_length_cjk,
            cancel_event=cancel_event,
        )

    async def _process_media_lyrics_align_task(
        self,
        db: Session,
        task: ProcessingTask,
        media_item: MediaItem,
        *,
        cancel_event: threading.Event | None = None,
    ):
        vocals_path = self._existing_local_file(media_item.vocals_path)
        if vocals_path is None:
            raise RuntimeError("Existing vocals sidecar is required for lyrics alignment")
        lyrics_text, lyrics_format = self._alignment_lyrics_for_media(media_item)
        if not lyrics_text:
            raise RuntimeError("Plain or LRC lyrics are required for lyrics alignment")

        demucs_health = self.demucs_client.health_check()
        if not demucs_health.healthy:
            raise RuntimeError(
                f"Demucs unavailable at {demucs_health.api_url}: {demucs_health.detail}"
            )

        await self._raise_if_canceled(cancel_event, task.id)
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.PROCESSING,
            stage="whisperx",
            progress_label="Aligning lyrics",
            progress_label_key="task.aligning_lyrics",
            progress_percent=0,
            progress_step_index=1,
            progress_step_total=1,
        )
        loop = asyncio.get_running_loop()
        progress_callback = self._demucs_progress_callback(
            loop,
            task.id,
            step_index=1,
            step_total=1,
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="whisperx",
            queue_item_id=None,
            has_whisperx=True,
        )
        log_callback = self._log_callback(
            loop,
            task.id,
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="whisperx",
        )
        align_language, detect_language = self._resolve_whisperx_alignment_settings(
            whisperx_align_language_override=task.whisperx_align_language_override
        )
        aligned_lyrics_path, remote_job_id = await self.demucs_client.align_lyrics(
            vocals_path,
            output_dir=self._task_cache_dir("demucs_outputs", task.id),
            lyrics_text=lyrics_text,
            lyrics_format=lyrics_format,
            transcription_model=settings.whisperx_transcription_model,
            align_language=align_language,
            detect_language=detect_language,
            use_synced_lyrics=settings.whisperx_use_synced_lyrics,
            process_lyrics_lines=bool(task.process_lyrics_lines),
            max_line_length=task.max_line_length,
            max_line_length_cjk=task.max_line_length_cjk,
            whisperx_preload_models=settings.whisperx_preload_models,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
        await self._raise_if_canceled(cancel_event, task.id)
        media_stem = self._media_stem_for_media(
            media_item,
            fallback=media_item.youtube_id or f"media-{media_item.id}",
        )
        final_lyrics_path = await asyncio.to_thread(
            self._install_aligned_lyrics_sidecar,
            media_stem,
            aligned_lyrics_path,
        )
        media_item.lyrics_path = QueueService.build_media_url(final_lyrics_path)
        media_item.missing = False
        db.commit()
        await processing_task_service.set_status(
            db,
            task.id,
            status=ProcessingTaskStatus.DONE,
            stage="ready",
            progress_label="Ready",
            progress_label_key="task.ready",
            progress_percent=100,
        )
        self._cleanup_remote_demucs_job(remote_job_id, task_id=task.id, stage="whisperx")

    async def _prepare_karaoke_inputs(
        self,
        db: Session,
        task: ProcessingTask,
        media_item: MediaItem,
        *,
        existing_media_path: Path | None,
        queue_item_id: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> tuple[Path, Path]:
        media_stem = self._media_stem_for_media(
            media_item,
            fallback=media_item.youtube_id or f"media-{media_item.id}",
        )
        loop = asyncio.get_running_loop()
        if existing_media_path:
            await self._raise_if_canceled(cancel_event, task.id)
            existing_has_audio = self.ffmpeg.has_audio_stream(existing_media_path)
            if not existing_has_audio:
                if media_item.youtube_id:
                    logger.warning(
                        "Existing media has no audio stream; downloading fresh audio for Demucs "
                        "task_id=%s media_id=%s media_path=%s youtube_id=%s",
                        task.id,
                        media_item.id,
                        existing_media_path,
                        media_item.youtube_id,
                    )
                    await processing_task_service.set_stage(
                        db,
                        task.id,
                        status=ProcessingTaskStatus.DOWNLOADING,
                        stage="download",
                        progress_label="Downloading audio",
                        progress_label_key="task.downloading_audio",
                        progress_percent=0,
                        progress_step_index=1,
                        progress_step_total=3,
                    )
                    audio_path = await asyncio.to_thread(
                        lambda: self._download_audio_for_task(
                            media_item.youtube_id,
                            self._task_cache_dir("ytdlp", task.id),
                            loop,
                            task.id,
                            queue_item_id,
                            step_index=1,
                            step_total=3,
                            cancel_event=cancel_event,
                        )
                    )
                    await self._raise_if_canceled(cancel_event, task.id)
                    audio_path = await asyncio.to_thread(
                        self._rename_downloaded_file,
                        audio_path,
                        media_stem,
                        "audio",
                    )
                    return existing_media_path, audio_path
                raise RuntimeError("Media file has no audio stream for Demucs input")

            if self._should_use_direct_media_input(existing_media_path, has_audio=existing_has_audio):
                logger.info(
                    "Using direct media for Demucs media_path=%s size_bytes=%s cutoff_mb=%s",
                    existing_media_path,
                    self._local_file_size_bytes(existing_media_path),
                    settings.demucs_direct_media_max_mb,
                )
                await processing_task_service.set_stage(
                    db,
                    task.id,
                    status=ProcessingTaskStatus.PROCESSING,
                    stage="demucs",
                    progress_label="Separating vocals",
                    progress_label_key="task.separating_vocals",
                    progress_percent=0,
                    progress_step_index=1,
                    progress_step_total=3,
                )
                return existing_media_path, existing_media_path

            await processing_task_service.set_stage(
                db,
                task.id,
                status=ProcessingTaskStatus.PROCESSING,
                stage="extract_audio",
                progress_label="Extracting audio",
                progress_label_key="task.extracting_audio",
                progress_percent=0,
                progress_step_index=1,
                progress_step_total=3,
            )
            extracted_audio_path = self._task_cache_dir("audio", task.id) / f"{media_stem}.audio.m4a"
            audio_path = await asyncio.to_thread(
                lambda: self.ffmpeg.extract_audio(
                    existing_media_path,
                    extracted_audio_path,
                    cancel_event=cancel_event,
                )
            )
            await self._raise_if_canceled(cancel_event, task.id)
            await processing_task_service.emit_progress(
                task.id,
                progress_percent=100,
                progress_label="Extracting audio",
                progress_label_key="task.extracting_audio",
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="extract_audio",
                progress_step_index=1,
                progress_step_total=3,
            )
            await processing_task_service.emit_log(
                task.id,
                message=f"Extracted audio to {audio_path.name}",
                stream="system",
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="extract_audio",
                progress_percent=100,
                progress_label="Extracting audio",
                progress_label_key="task.extracting_audio",
                progress_step_index=1,
                progress_step_total=3,
            )
            return existing_media_path, audio_path

        if not media_item.youtube_id:
            raise RuntimeError("Missing YouTube source for karaoke preparation")

        processing_dir = self._task_cache_dir("ytdlp", task.id)
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
            progress_label="Downloading video",
            progress_label_key="task.downloading_video",
            progress_percent=0,
            progress_step_index=1,
            progress_step_total=4,
        )
        video_path = await asyncio.to_thread(
            lambda: self._download_video_for_task(
                media_item.youtube_id,
                processing_dir,
                loop,
                task.id,
                queue_item_id,
                step_index=1,
                step_total=4,
                cancel_event=cancel_event,
            )
        )
        await self._raise_if_canceled(cancel_event, task.id)
        video_path = await asyncio.to_thread(
            self._rename_downloaded_file,
            video_path,
            media_stem,
            "media",
        )
        await self._raise_if_canceled(cancel_event, task.id)
        downloaded_video_has_audio = self.ffmpeg.has_audio_stream(video_path)
        if not downloaded_video_has_audio:
            logger.warning(
                "Downloaded video has no audio stream; downloading separate audio for Demucs "
                "task_id=%s media_id=%s media_path=%s youtube_id=%s",
                task.id,
                media_item.id,
                video_path,
                media_item.youtube_id,
            )
        if self._should_use_direct_media_input(video_path, has_audio=downloaded_video_has_audio):
            logger.info(
                "Using direct media for Demucs media_path=%s size_bytes=%s cutoff_mb=%s",
                video_path,
                self._local_file_size_bytes(video_path),
                settings.demucs_direct_media_max_mb,
            )
            await processing_task_service.set_stage(
                db,
                task.id,
                status=ProcessingTaskStatus.PROCESSING,
                stage="demucs",
                progress_label="Separating vocals",
                progress_label_key="task.separating_vocals",
                progress_percent=0,
                progress_step_index=3,
                progress_step_total=4,
            )
            return video_path, video_path
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
            progress_label="Downloading audio",
            progress_label_key="task.downloading_audio",
            progress_percent=0,
            progress_step_index=2,
            progress_step_total=4,
        )
        audio_path = await asyncio.to_thread(
            lambda: self._download_audio_for_task(
                media_item.youtube_id,
                processing_dir,
                loop,
                task.id,
                queue_item_id,
                step_index=2,
                step_total=4,
                cancel_event=cancel_event,
            )
        )
        await self._raise_if_canceled(cancel_event, task.id)
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
        align_lyrics: bool = False,
        whisperx_align_language_override: str | None = None,
        process_lyrics_lines: bool | None = None,
        max_line_length: int | None = None,
        max_line_length_cjk: int | None = None,
        cancel_event: threading.Event | None = None,
    ):
        await self._raise_if_canceled(cancel_event, task.id)
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.PROCESSING,
            stage="demucs",
            progress_label="Separating vocals",
            progress_label_key="task.separating_vocals",
            progress_percent=0,
            progress_step_index=3,
            progress_step_total=4,
        )
        demucs_response = await self._separate_vocals_with_retry(
            queue_item,
            media_item,
            audio_path,
            align_lyrics=align_lyrics,
            task_id=task.id,
            whisperx_align_language_override=whisperx_align_language_override,
            process_lyrics_lines=process_lyrics_lines,
            max_line_length=max_line_length,
            max_line_length_cjk=max_line_length_cjk,
            progress_step_index=3,
            progress_step_total=4,
            cancel_event=cancel_event,
        )
        no_vocals_path = Path(demucs_response.no_vocals_path)
        vocals_raw_path = Path(demucs_response.vocals_path) if demucs_response.vocals_path else None
        raw_aligned_lyrics_path = getattr(demucs_response, "aligned_lyrics_path", None)
        aligned_lyrics_path = (
            Path(raw_aligned_lyrics_path)
            if isinstance(raw_aligned_lyrics_path, (str, os.PathLike))
            and str(raw_aligned_lyrics_path).strip()
            else None
        )
        if not no_vocals_path.exists():
            raise RuntimeError("Demucs response missing no-vocals output path")
        if vocals_raw_path is None or not vocals_raw_path.exists():
            raise RuntimeError("Demucs response missing vocals output path")
        if aligned_lyrics_path is not None and not aligned_lyrics_path.exists():
            logger.warning(
                "Demucs response missing aligned lyrics sidecar media_id=%s path=%s",
                media_item.id,
                aligned_lyrics_path,
            )
            aligned_lyrics_path = None
        if align_lyrics and aligned_lyrics_path is None:
            raise RuntimeError("Demucs response missing aligned lyrics output path")
        await self._raise_if_canceled(cancel_event, task.id)
        await processing_task_service.emit_progress(
            task.id,
            queue_item_id=queue_item.id if queue_item is not None else None,
            progress_percent=100,
            progress_label="Separating vocals",
            progress_label_key="task.separating_vocals",
            status=ProcessingTaskStatus.PROCESSING.value,
            stage="demucs",
            progress_step_index=3,
            progress_step_total=4,
        )
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.PROCESSING,
            stage="finalize",
            progress_label="Remuxing karaoke media",
            progress_label_key="task.finalizing_karaoke",
            progress_percent=0,
            progress_step_index=4,
            progress_step_total=4,
        )
        media_stem = self._media_stem_for_media(
            media_item,
            fallback=media_item.youtube_id or f"media-{media_item.id}",
        )
        if self._is_audio_only_media_path(video_path):
            output_path = no_vocals_path
        else:
            output_path = self._task_cache_dir("processed", task.id) / f"{media_stem}.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if cancel_event is None:
                await asyncio.to_thread(
                    lambda: self.ffmpeg.combine_audio_video(
                        video_path=video_path,
                        audio_path=no_vocals_path,
                        output_path=output_path,
                        audio_codec=settings.ffmpeg_audio_codec,
                    )
                )
            else:
                await asyncio.to_thread(
                    lambda: self.ffmpeg.combine_audio_video(
                        video_path=video_path,
                        audio_path=no_vocals_path,
                        output_path=output_path,
                        audio_codec=settings.ffmpeg_audio_codec,
                        cancel_event=cancel_event,
                    )
                )
        await self._raise_if_canceled(cancel_event, task.id)
        original_media_path = self._existing_local_file(media_item.media_path)
        final_media_path, vocals_sidecar_path = await asyncio.to_thread(
            self._install_karaoke_outputs,
            media_stem=media_stem,
            primary_source=output_path,
            vocals_source=vocals_raw_path,
            task_id=task.id,
        )
        final_lyrics_path = None
        if aligned_lyrics_path is not None:
            final_lyrics_path = await asyncio.to_thread(
                self._install_aligned_lyrics_sidecar,
                media_stem,
                aligned_lyrics_path,
            )
        self._set_media_item_output_paths(
            db,
            media_item,
            media_path=final_media_path,
            vocals_path=vocals_sidecar_path,
            lyrics_path=final_lyrics_path,
        )
        if original_media_path is not None and original_media_path != final_media_path:
            from services.media_thumbnail_service import MediaThumbnailService

            thumbnail_service = MediaThumbnailService()
            thumbnail_service.ensure_thumbnail_for_media_file(original_media_path)
            thumbnail_service.rename_thumbnail_for_media_file(
                original_media_path,
                final_media_path,
            )
            self._remove_path(original_media_path)
        await processing_task_service.set_status(
            db,
            task.id,
            status=ProcessingTaskStatus.DONE,
            stage="ready",
            progress_label="Ready",
            progress_label_key="task.ready",
            progress_percent=100,
        )
        self._cleanup_remote_demucs_job(demucs_response.job_id, task_id=task.id, stage="demucs")

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

    def _is_audio_only_media_path(self, media_path: Path) -> bool:
        """Return whether the file contains no video stream."""
        if media_path.suffix.lower() in _AUDIO_EXTENSIONS:
            return True
        return not self.ffmpeg.has_video_stream(media_path)

    @staticmethod
    def _alignment_lyrics_for_media(media_item: MediaItem) -> tuple[str | None, str | None]:
        """Return lyrics text and format suitable for WhisperX alignment."""
        lyrics_path = KaraokeService._existing_local_file(media_item.lyrics_path)
        if lyrics_path is None or lyrics_path.suffix.lower() not in {".lrc", ".txt"}:
            return None, None
        try:
            lyrics_text = lyrics_path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning(
                "Failed to read lyrics sidecar for alignment media_id=%s path=%s",
                media_item.id,
                lyrics_path,
            )
            return None, None
        if not lyrics_text:
            return None, None
        lyrics_format = "lrc" if lyrics_path.suffix.lower() == ".lrc" else "txt"
        return lyrics_text, lyrics_format

    @staticmethod
    def _local_file_size_bytes(media_path: Path) -> int:
        """Return the current local file size in bytes."""
        return media_path.stat().st_size

    def _should_use_direct_media_input(
        self,
        media_path: Path,
        *,
        has_audio: bool | None = None,
    ) -> bool:
        """Return whether the file should be sent directly to Demucs."""
        if has_audio is None:
            has_audio = self.ffmpeg.has_audio_stream(media_path)
        if not has_audio:
            return False
        if self._is_audio_only_media_path(media_path):
            return True
        cutoff_mb = max(0, settings.demucs_direct_media_max_mb)
        cutoff_bytes = cutoff_mb * 1024 * 1024
        try:
            return KaraokeService._local_file_size_bytes(media_path) <= cutoff_bytes
        except OSError:
            logger.warning(
                "Failed to stat media file for direct-media cutoff media_path=%s",
                media_path,
            )
            return False

    @staticmethod
    def _install_karaoke_outputs(
        *,
        media_stem: str,
        primary_source: Path,
        vocals_source: Path,
        task_id: int,
    ) -> tuple[Path, Path]:
        """Stage both karaoke outputs before replacing durable media files."""
        primary_extension = primary_source.suffix.lower() or ".wav"
        vocals_extension = vocals_source.suffix.lower() or ".wav"
        primary_target = settings.media_path / f"{media_stem}{primary_extension}"
        vocals_target = settings.media_path / f"{media_stem}.vocals{vocals_extension}"
        primary_temp = settings.media_path / f".{media_stem}.{task_id}.primary.tmp{primary_extension}"
        vocals_temp = settings.media_path / f".{media_stem}.{task_id}.vocals.tmp{vocals_extension}"
        settings.media_path.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(primary_source, primary_temp)
            shutil.copy2(vocals_source, vocals_temp)
            os.replace(vocals_temp, vocals_target)
            os.replace(primary_temp, primary_target)
        finally:
            for temp_path in (primary_temp, vocals_temp):
                if temp_path.exists():
                    temp_path.unlink()

        return primary_target, vocals_target

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

    @staticmethod
    def _resolve_whisperx_alignment_settings(
        queue_item: QueueItem | None = None,
        *,
        whisperx_align_language_override: str | None = None,
    ) -> tuple[str | None, bool]:
        """Return the WhisperX language settings for one queue item or media task."""
        align_language = settings.whisperx_align_language
        detect_language = settings.whisperx_detect_language
        task_override = (whisperx_align_language_override or "").strip().lower()
        if task_override:
            return task_override, False
        if queue_item is None:
            return align_language, detect_language

        override_language = (queue_item.whisperx_align_language_override or "").strip().lower()
        if override_language:
            return override_language, False
        return align_language, detect_language

    @staticmethod
    def _line_processing_settings(
        queue_item: QueueItem | None,
        *,
        process_lyrics_lines: bool | None = None,
        max_line_length: int | None = None,
        max_line_length_cjk: int | None = None,
    ) -> tuple[bool, int | None, int | None]:
        if queue_item is not None:
            if not bool(queue_item.process_lyrics_lines):
                return False, None, None
            return True, queue_item.max_line_length or 36, queue_item.max_line_length_cjk or 12
        if not bool(process_lyrics_lines):
            return False, None, None
        return True, max_line_length or 36, max_line_length_cjk or 12

    async def _separate_vocals_with_retry(
        self,
        queue_item: QueueItem | None,
        media_item: MediaItem,
        audio_path: Path,
        *,
        align_lyrics: bool,
        task_id: int,
        whisperx_align_language_override: str | None = None,
        process_lyrics_lines: bool | None = None,
        max_line_length: int | None = None,
        max_line_length_cjk: int | None = None,
        progress_step_index: int,
        progress_step_total: int,
        cancel_event: threading.Event | None = None,
    ):
        """Run Demucs separation with one fallback retry for extracted local audio."""
        lyrics_text, lyrics_format = (
            self._alignment_lyrics_for_media(media_item)
            if align_lyrics
            else (None, None)
        )
        if align_lyrics and not lyrics_text:
            raise RuntimeError("Plain or LRC lyrics are required for lyrics alignment")
        align_language, detect_language = self._resolve_whisperx_alignment_settings(
            queue_item,
            whisperx_align_language_override=whisperx_align_language_override,
        )

        async def run_demucs(target_audio_path: Path):
            line_processing_enabled, processing_max_line_length, processing_max_line_length_cjk = self._line_processing_settings(
                queue_item,
                process_lyrics_lines=process_lyrics_lines,
                max_line_length=max_line_length,
                max_line_length_cjk=max_line_length_cjk,
            )
            demucs_kwargs = {
                "output_dir": self._task_cache_dir("demucs_outputs", task_id),
                "lyrics_text": lyrics_text,
                "lyrics_format": lyrics_format,
                "transcription_model": settings.whisperx_transcription_model,
                "align_language": align_language,
                "detect_language": detect_language,
                "use_synced_lyrics": settings.whisperx_use_synced_lyrics,
                "whisperx_preload_models": settings.whisperx_preload_models,
                "process_lyrics_lines": line_processing_enabled,
                "max_line_length": processing_max_line_length,
                "max_line_length_cjk": processing_max_line_length_cjk,
                "progress_callback": progress_callback,
                "log_callback": log_callback,
            }
            if cancel_event is not None:
                demucs_kwargs["cancel_event"] = cancel_event
            return await self.demucs_client.separate_vocals(target_audio_path, **demucs_kwargs)

        try:
            await KaraokeService._raise_if_canceled(cancel_event, task_id)
            loop = asyncio.get_running_loop()
            progress_callback = self._demucs_progress_callback(
                loop,
                task_id,
                step_index=progress_step_index,
                step_total=progress_step_total,
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="demucs",
                queue_item_id=queue_item.id if queue_item is not None else None,
                has_whisperx=bool(lyrics_text),
            )
            log_callback = self._log_callback(
                loop,
                task_id,
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="demucs",
            )
            return await run_demucs(audio_path)
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code if error.response is not None else None
            can_retry = (
                status_code is not None
                and status_code >= 500
                and audio_path.suffix.lower() == ".m4a"
                and bool(media_item.youtube_id)
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
                progress_label_key="task.retrying_demucs_preparation",
                progress_step_index=progress_step_index,
                progress_step_total=progress_step_total,
            )
            processing_dir = self._task_cache_dir("ytdlp", task_id)
            if cancel_event is None:
                fallback_audio_path = await asyncio.to_thread(
                    lambda: self.youtube_service.download_audio(
                        media_item.youtube_id,
                        processing_dir,
                    )
                )
            else:
                fallback_audio_path = await asyncio.to_thread(
                    lambda: self.youtube_service.download_audio(
                        media_item.youtube_id,
                        processing_dir,
                        cancel_event=cancel_event,
                    )
                )
            await KaraokeService._raise_if_canceled(cancel_event, task_id)
            loop = asyncio.get_running_loop()
            progress_callback = self._demucs_progress_callback(
                loop,
                task_id,
                step_index=progress_step_index,
                step_total=progress_step_total,
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="demucs",
                queue_item_id=queue_item.id if queue_item is not None else None,
                has_whisperx=bool(lyrics_text),
            )
            log_callback = self._log_callback(
                loop,
                task_id,
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="demucs",
            )
            return await run_demucs(fallback_audio_path)

    @staticmethod
    def _set_media_item_media_path(db: Session, media_item: MediaItem, media_path: Path):
        media_item.media_path = QueueService.build_media_url(media_path)
        media_item.missing = False
        db.commit()

    @staticmethod
    def _set_media_item_output_paths(
        db: Session,
        media_item: MediaItem,
        *,
        media_path: Path,
        vocals_path: Path,
        lyrics_path: Path | None = None,
    ):
        media_item.media_path = QueueService.build_media_url(media_path)
        media_item.vocals_path = QueueService.build_media_url(vocals_path)
        if lyrics_path is not None:
            media_item.lyrics_path = QueueService.build_media_url(lyrics_path)
        media_item.missing = False
        db.commit()

    @staticmethod
    def _install_aligned_lyrics_sidecar(media_stem: str, source_path: Path) -> Path:
        """Persist aligned lyrics JSON beside the durable media output."""
        target_path = settings.media_path / f"{media_stem}.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        return target_path

    def cleanup_canceled_task(self, db: Session, task: ProcessingTask):
        """Remove generated outputs and reset rows for a canceled task."""
        media_item = self._media_item_for_task(db, task)
        if media_item is None:
            return

        media_stem = self._media_stem_for_media(
            media_item,
            fallback=media_item.youtube_id or f"media-{media_item.id}",
        )

        preserve_durable_media = (
            task.task_type in {"media_karaoke", "media_karaoke_align", "media_lyrics_align"}
            or task.source_kind == "library_media"
        )
        paths_to_remove = self._cached_task_paths(media_stem)
        self._remove_task_cache_dirs(task)
        paths_to_remove.extend(
            path
            for path in settings.media_path.glob(f".{media_stem}.{task.id}.*.tmp*")
            if path.is_file()
        )
        if not preserve_durable_media:
            for media_url in (media_item.media_path, media_item.vocals_path):
                media_file = QueueService._media_url_to_file(media_url)
                if media_file is not None:
                    paths_to_remove.append(media_file)
            paths_to_remove.extend(
                path for path in settings.media_path.glob(f"{media_stem}*") if path.is_file()
            )

        for path in paths_to_remove:
            self._remove_path(path)

        from services.media_thumbnail_service import MediaThumbnailService

        if not preserve_durable_media and media_item.media_path:
            media_file = QueueService._media_url_to_file(media_item.media_path)
            if media_file is not None:
                MediaThumbnailService().remove_thumbnail_for_media_file(media_file)

        if media_item.vocals_path:
            vocals_file = QueueService._media_url_to_file(media_item.vocals_path)
            if vocals_file is not None and not vocals_file.exists():
                media_item.vocals_path = None

        if task.target_queue_item_id is not None:
            queue_item = (
                db.query(QueueItem)
                .filter(QueueItem.id == task.target_queue_item_id)
                .first()
            )
            if queue_item is not None:
                queue_item.status = "pending"
                queue_item.error = None

        current_media_file = QueueService._media_url_to_file(media_item.media_path)
        media_item.missing = current_media_file is None or not current_media_file.exists()
        db.commit()

    def cleanup_successful_task(self, task: ProcessingTask) -> None:
        """Remove task-owned scratch data after durable finalization succeeds."""
        categories = (
            ("demucs_outputs",)
            if task.task_type
            in {"media_vocal_sync_prepare_youtube", "media_vocal_sync_prepare_upload"}
            else ("ytdlp", "audio", "processed", "demucs_outputs")
        )
        self._remove_task_cache_dirs(task, categories=categories)

    def _cleanup_remote_demucs_job(self, job_id: str | None, *, task_id: int, stage: str) -> None:
        if not job_id:
            return
        try:
            self.demucs_client.delete_job_artifacts(job_id)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            logger.warning(
                "Failed to delete remote Demucs job artifacts task_id=%s stage=%s job_id=%s status_code=%s",
                task_id,
                stage,
                job_id,
                status_code,
            )
        except Exception:
            logger.exception(
                "Failed to delete remote Demucs job artifacts task_id=%s stage=%s job_id=%s",
                task_id,
                stage,
                job_id,
            )

    @staticmethod
    def _remove_task_cache_dirs(
        task: ProcessingTask,
        *,
        categories: tuple[str, ...] = ("ytdlp", "audio", "processed", "demucs_outputs"),
    ) -> None:
        for category in categories:
            task_dir = settings.cache_path / category / str(task.id)
            try:
                if task_dir.is_dir():
                    shutil.rmtree(task_dir)
            except OSError:
                logger.exception(
                    "Failed to remove task cache directory task_id=%s category=%s path=%s",
                    task.id,
                    category,
                    task_dir,
                )

    def _cached_task_paths(self, media_stem: str) -> list[Path]:
        """Collect temporary cache paths that belong to a task stem."""
        candidates: list[Path] = []
        cache_roots = [
            settings.cache_path / "ytdlp",
            settings.cache_path / "audio",
            settings.cache_path / "processed",
            settings.cache_path / "demucs_outputs",
        ]
        for root in cache_roots:
            if not root.exists():
                continue
            candidates.extend(path for path in root.glob(f"{media_stem}*") if path.is_file())
        return candidates

    @staticmethod
    def _remove_path(path: Path | None):
        if path is None:
            return
        try:
            if path.exists():
                path.unlink()
        except OSError:
            logger.exception("Failed to remove canceled task path=%s", path)

    def _media_item_for_task(self, db: Session, task: ProcessingTask) -> MediaItem | None:
        if task.target_media_item_id is not None:
            return (
                db.query(MediaItem)
                .filter(MediaItem.id == task.target_media_item_id)
                .first()
            )
        if task.target_queue_item_id is None:
            return None
        queue_item = (
            db.query(QueueItem)
            .filter(QueueItem.id == task.target_queue_item_id)
            .first()
        )
        return queue_item.media if queue_item is not None else None

    async def _finalize_cancellation(self, db: Session, task: ProcessingTask):
        """Persist cancel status and reset related queue/media state."""
        current = processing_task_service.get_task(db, task.id)
        if current is None:
            return
        if current.status != ProcessingTaskStatus.CANCELED.value:
            await processing_task_service.set_canceled(
                db,
                task.id,
                stage=task.stage or "canceled",
                progress_label="Task canceled",
                progress_label_key="task.canceled",
            )
        self.cleanup_canceled_task(db, task)

    async def _process_media_vocal_sync_prepare_task(
        self,
        db: Session,
        task: ProcessingTask,
        media_item: MediaItem,
        *,
        cancel_event: threading.Event | None = None,
    ) -> None:
        manifest = self.vocal_sync_service.read_task_manifest(task.id)
        youtube_id = str(manifest.get("youtube_id") or "").strip()
        if not youtube_id:
            raise RuntimeError("Vocal sync task is missing the selected YouTube source")

        self.vocal_sync_service.validate_media_item_for_prepare(db, media_item.id)
        self.vocal_sync_service._check_demucs_available()
        loop = asyncio.get_running_loop()
        await processing_task_service.set_stage(
            db,
            task.id,
            status=ProcessingTaskStatus.DOWNLOADING,
            stage="download",
            progress_label="Downloading audio",
            progress_label_key="task.downloading_audio",
            progress_percent=0,
            progress_step_index=1,
            progress_step_total=3,
        )
        session, remote_job_id = await self.vocal_sync_service.prepare_from_youtube(
            db,
            media_item.id,
            youtube_id,
            cancel_event=cancel_event,
            download_progress_callback=self._progress_callback(
                loop,
                task.id,
                "Downloading audio",
                label_key="task.downloading_audio",
                step_index=1,
                step_total=3,
                status=ProcessingTaskStatus.DOWNLOADING.value,
                stage="download",
            ),
            download_log_callback=self._log_callback(
                loop,
                task.id,
                status=ProcessingTaskStatus.DOWNLOADING.value,
                stage="download",
            ),
            demucs_progress_callback=self._demucs_progress_callback(
                loop,
                task.id,
                step_index=2,
                step_total=3,
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="demucs",
                has_whisperx=False,
            ),
            demucs_log_callback=self._log_callback(
                loop,
                task.id,
                status=ProcessingTaskStatus.PROCESSING.value,
                stage="demucs",
            ),
            before_finalize=lambda: self._dispatch_loop_coroutine(
                loop,
                processing_task_service.set_stage(
                    db,
                    task.id,
                    status=ProcessingTaskStatus.PROCESSING,
                    stage="finalize",
                    progress_label="Finalizing vocals",
                    progress_label_key="task.finalizing_vocal_sync",
                    progress_percent=0,
                    progress_step_index=3,
                    progress_step_total=3,
                ),
            ),
            demucs_output_dir=self._task_cache_dir("demucs_outputs", task.id),
        )
        self.vocal_sync_service.update_task_manifest_session(task.id, session.session_id)
        await self._raise_if_canceled(cancel_event, task.id)
        await processing_task_service.set_status(
            db,
            task.id,
            status=ProcessingTaskStatus.DONE,
            stage="ready",
            progress_label="Ready",
            progress_label_key="task.ready",
            progress_percent=100,
            progress_step_index=3,
            progress_step_total=3,
        )
        self._cleanup_remote_demucs_job(remote_job_id, task_id=task.id, stage="demucs")

    async def _process_media_vocal_sync_prepare_upload_task(
        self,
        db: Session,
        task: ProcessingTask,
        media_item: MediaItem,
        *,
        cancel_event: threading.Event | None = None,
    ) -> None:
        manifest = self.vocal_sync_service.read_task_manifest(task.id)
        source_filename = str(manifest.get("source_filename") or "").strip()
        source_path_raw = str(manifest.get("source_path") or "").strip()
        if not source_filename or not source_path_raw:
            raise RuntimeError("Vocal sync upload task is missing the uploaded source")
        source_path = Path(source_path_raw)

        self.vocal_sync_service.validate_media_item_for_prepare(db, media_item.id)
        self.vocal_sync_service._check_demucs_available()
        loop = asyncio.get_running_loop()
        try:
            await processing_task_service.set_stage(
                db,
                task.id,
                status=ProcessingTaskStatus.PROCESSING,
                stage="demucs",
                progress_label="Separating vocals",
                progress_label_key="task.separating_vocals",
                progress_percent=0,
                progress_step_index=1,
                progress_step_total=2,
            )
            session, remote_job_id = await self.vocal_sync_service.prepare_from_staged_upload(
                db,
                media_item.id,
                source_filename=source_filename,
                source_path=source_path,
                cancel_event=cancel_event,
                demucs_progress_callback=self._demucs_progress_callback(
                    loop,
                    task.id,
                    step_index=1,
                    step_total=2,
                    status=ProcessingTaskStatus.PROCESSING.value,
                    stage="demucs",
                    has_whisperx=False,
                ),
                demucs_log_callback=self._log_callback(
                    loop,
                    task.id,
                    status=ProcessingTaskStatus.PROCESSING.value,
                    stage="demucs",
                ),
                before_finalize=lambda: self._dispatch_loop_coroutine(
                    loop,
                    processing_task_service.set_stage(
                        db,
                        task.id,
                        status=ProcessingTaskStatus.PROCESSING,
                        stage="finalize",
                        progress_label="Finalizing vocals",
                        progress_label_key="task.finalizing_vocal_sync",
                        progress_percent=0,
                        progress_step_index=2,
                        progress_step_total=2,
                    ),
                ),
                demucs_output_dir=self._task_cache_dir("demucs_outputs", task.id),
            )
            self.vocal_sync_service.update_task_manifest_session(task.id, session.session_id)
            await self._raise_if_canceled(cancel_event, task.id)
            await processing_task_service.set_status(
                db,
                task.id,
                status=ProcessingTaskStatus.DONE,
                stage="ready",
                progress_label="Ready",
                progress_label_key="task.ready",
                progress_percent=100,
                progress_step_index=2,
                progress_step_total=2,
            )
            self._cleanup_remote_demucs_job(remote_job_id, task_id=task.id, stage="demucs")
        finally:
            self.vocal_sync_service.cleanup_task_source(task.id)

    @staticmethod
    def _dispatch_loop_coroutine(loop: asyncio.AbstractEventLoop, coroutine) -> None:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is loop:
            loop.create_task(coroutine)
            return

        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        future.result(timeout=5)

    @staticmethod
    def _progress_callback(
        loop: asyncio.AbstractEventLoop,
        task_id: int,
        label: str,
        *,
        label_key: str,
        step_index: int,
        step_total: int,
        status: str,
        stage: str,
        queue_item_id: int | None = None,
    ):
        last_emit_time = float("-inf")
        last_emit_percent: int | None = None

        def callback(percent: int, raw_line: str):
            nonlocal last_emit_time, last_emit_percent
            mapped = max(0, min(100, int(percent)))
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
            KaraokeService._dispatch_loop_coroutine(
                loop,
                processing_task_service.emit_progress(
                    task_id,
                    queue_item_id=queue_item_id,
                    progress_percent=mapped,
                    progress_label=label,
                    progress_label_key=label_key,
                    status=status,
                    stage=stage,
                    progress_step_index=step_index,
                    progress_step_total=step_total,
                ),
            )
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
            KaraokeService._dispatch_loop_coroutine(
                loop,
                processing_task_service.emit_log(
                    task_id,
                    message=message,
                    stream=stream,
                    status=status,
                    stage=stage,
                ),
            )
        return callback

    @staticmethod
    def _demucs_progress_callback(
        loop: asyncio.AbstractEventLoop,
        task_id: int,
        *,
        step_index: int,
        step_total: int,
        status: str,
        stage: str,
        queue_item_id: int | None = None,
        has_whisperx: bool = False,
    ):
        whisperx_label_keys = {
            "whisperx_loading_audio": ("Loading audio", "task.whisperx_loading_audio"),
            "whisperx_loading_model": ("Loading WhisperX model", "task.whisperx_loading_model"),
            "whisperx_detecting_language": ("Detecting language", "task.whisperx_detecting_language"),
            "whisperx_loading_alignment_model": (
                "Loading alignment model",
                "task.whisperx_loading_alignment_model",
            ),
            "whisperx_aligning_lyrics": ("Aligning lyrics", "task.whisperx_aligning_lyrics"),
        }
        last_emit_time = float("-inf")
        last_emit_percent: int | None = None
        last_emit_message: str | None = None
        last_logged_job_message: str | None = None
        current_stage = stage
        whisperx_started = False

        def callback(percent: int, message: str, metadata: dict | None = None):
            nonlocal current_stage, last_emit_time, last_emit_percent
            nonlocal last_emit_message, last_logged_job_message, whisperx_started
            mapped = max(0, min(100, int(percent)))
            current_message = message or "Separating vocals"
            metadata_stage = str(metadata.get("progress_stage") or "") if metadata else ""
            progress_mode = str(metadata.get("progress_mode") or "determinate") if metadata else "determinate"
            if has_whisperx and metadata_stage == "whisperx" and not whisperx_started:
                whisperx_started = True
                KaraokeService._dispatch_loop_coroutine(
                    loop,
                    processing_task_service.emit_progress(
                        task_id,
                        queue_item_id=queue_item_id,
                        progress_percent=100,
                        progress_label="Separating vocals",
                        progress_label_key="task.separating_vocals",
                        progress_mode="determinate",
                        status=status,
                        stage="demucs",
                        progress_step_index=step_index,
                        progress_step_total=step_total,
                    ),
                )
                current_stage = "whisperx"
            elif (
                has_whisperx
                and not whisperx_started
                and current_message == "Aligning lyrics"
                and mapped >= 95
            ):
                whisperx_started = True
                KaraokeService._dispatch_loop_coroutine(
                    loop,
                    processing_task_service.emit_progress(
                        task_id,
                        queue_item_id=queue_item_id,
                        progress_percent=100,
                        progress_label="Separating vocals",
                        progress_label_key="task.separating_vocals",
                        progress_mode="determinate",
                        status=status,
                        stage="demucs",
                        progress_step_index=step_index,
                        progress_step_total=step_total,
                    ),
                )
                current_stage = "whisperx"
                mapped = 0
            elif metadata_stage in {"demucs", "whisperx"}:
                current_stage = metadata_stage
            elif whisperx_started and mapped < 100:
                current_stage = "whisperx"

            if current_stage == "whisperx":
                current_message, label_key = whisperx_label_keys.get(
                    current_message,
                    (current_message or "Aligning lyrics", "task.whisperx_aligning_lyrics"),
                )
                if progress_mode == "determinate" and mapped > 0 and mapped < 100:
                    mapped = 0
            else:
                label_key = "task.separating_vocals"
                progress_mode = "determinate"

            if whisperx_started and current_stage == "whisperx" and mapped < 100 and progress_mode != "indeterminate":
                current_message = "Aligning lyrics"
                label_key = "task.whisperx_aligning_lyrics"
                mapped = 0
            now = loop.time()
            if (
                last_emit_percent is not None
                and mapped != 100
                and mapped == last_emit_percent
                and current_message == last_emit_message
            ):
                return
            if (
                last_emit_percent is not None
                and mapped != 100
                and current_message == last_emit_message
                and (now - last_emit_time) < 0.75
            ):
                return
            last_emit_time = now
            last_emit_percent = mapped
            last_emit_message = current_message
            KaraokeService._dispatch_loop_coroutine(
                loop,
                processing_task_service.emit_progress(
                    task_id,
                    queue_item_id=queue_item_id,
                    progress_percent=mapped,
                    progress_label=current_message,
                    progress_label_key=label_key,
                    progress_mode=progress_mode,
                    status=status,
                    stage=current_stage,
                    progress_step_index=step_index,
                    progress_step_total=step_total,
                ),
            )
            job_id = metadata.get("job_id") if metadata else None
            log_message = f"Demucs job {job_id}: {current_message}" if job_id else None
            if log_message and log_message != last_logged_job_message:
                last_logged_job_message = log_message
                KaraokeService._dispatch_loop_coroutine(
                    loop,
                    processing_task_service.emit_log(
                        task_id,
                        message=log_message,
                        stream="remote",
                        status=status,
                        stage=current_stage,
                        progress_percent=mapped,
                        progress_label=current_message,
                        progress_label_key=label_key,
                        progress_mode=progress_mode,
                        progress_step_index=step_index,
                        progress_step_total=step_total,
                    ),
                )

        return callback

    def _download_video_for_task(
        self,
        youtube_id: str,
        output_dir: Path,
        loop: asyncio.AbstractEventLoop,
        task_id: int,
        queue_item_id: int | None = None,
        *,
        step_index: int,
        step_total: int,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        if isinstance(self.youtube_service, YouTubeService):
            kwargs = {}
            if cancel_event is not None:
                kwargs["cancel_event"] = cancel_event
            return self.youtube_service.download_video_with_progress(
                youtube_id,
                output_dir,
                progress_callback=self._progress_callback(loop, task_id, "Downloading video", label_key="task.downloading_video", step_index=step_index, step_total=step_total, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download", queue_item_id=queue_item_id),
                log_callback=self._log_callback(loop, task_id, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
                **kwargs,
            )
        if cancel_event is None:
            return self.youtube_service.download_video(youtube_id, output_dir)
        return self.youtube_service.download_video(youtube_id, output_dir, cancel_event=cancel_event)

    def _download_audio_for_task(
        self,
        youtube_id: str,
        output_dir: Path,
        loop: asyncio.AbstractEventLoop,
        task_id: int,
        queue_item_id: int | None = None,
        *,
        step_index: int,
        step_total: int,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        if isinstance(self.youtube_service, YouTubeService):
            kwargs = {}
            if cancel_event is not None:
                kwargs["cancel_event"] = cancel_event
            return self.youtube_service.download_audio_with_progress(
                youtube_id,
                output_dir,
                progress_callback=self._progress_callback(loop, task_id, "Downloading audio", label_key="task.downloading_audio", step_index=step_index, step_total=step_total, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download", queue_item_id=queue_item_id),
                log_callback=self._log_callback(loop, task_id, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
                **kwargs,
            )
        if cancel_event is None:
            return self.youtube_service.download_audio(youtube_id, output_dir)
        return self.youtube_service.download_audio(youtube_id, output_dir, cancel_event=cancel_event)

    def _download_video_with_audio_for_task(
        self,
        youtube_id: str,
        output_dir: Path,
        loop: asyncio.AbstractEventLoop,
        task_id: int,
        queue_item_id: int | None = None,
        *,
        step_index: int,
        step_total: int,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        if isinstance(self.youtube_service, YouTubeService):
            kwargs = {}
            if cancel_event is not None:
                kwargs["cancel_event"] = cancel_event
            return self.youtube_service.download_video_with_audio_progress(
                youtube_id,
                output_dir,
                progress_callback=self._progress_callback(loop, task_id, "Downloading media", label_key="task.downloading_media", step_index=step_index, step_total=step_total, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download", queue_item_id=queue_item_id),
                log_callback=self._log_callback(loop, task_id, status=ProcessingTaskStatus.DOWNLOADING.value, stage="download"),
                **kwargs,
            )
        if cancel_event is None:
            return self.youtube_service.download_video_with_audio(youtube_id, output_dir)
        return self.youtube_service.download_video_with_audio(youtube_id, output_dir, cancel_event=cancel_event)
