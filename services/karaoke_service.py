"""Karaoke service for orchestrating karaoke video generation."""
import asyncio
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from models import QueueItem
from services.youtube_service import YouTubeService
from services.lyrics_service import LyricsService
from services.demucs_client import DemucsClient
from services.queue_service import QueueService
from adapters.ffmpeg import FFmpegAdapter
from models import QueueStatus
from config import settings

logger = logging.getLogger(__name__)


class KaraokeService:
    """Service for orchestrating karaoke video generation."""

    def __init__(self):
        self.youtube_service = YouTubeService()
        self.lyrics_service = LyricsService()
        self.demucs_client = DemucsClient()
        self.queue_service = QueueService()
        self.ffmpeg = FFmpegAdapter()

    async def process_queue_item(self, db: Session, item_id: int):
        """
        Process a queue item end-to-end.

        Args:
            db: Database session
            item_id: Queue item ID
        """
        # Get item from database
        item = db.query(QueueItem).filter(QueueItem.id == item_id).first()
        if not item:
            logger.warning("Queue item not found for processing item_id=%s", item_id)
            return

        try:
            if item.media is None:
                raise RuntimeError(f"Queue item missing media for id={item.id}")
            existing_media_path = self._existing_media_file(item)
            existing_vocals_path = self._existing_local_file(item.media.vocals_path)
            logger.info(
                "Processing queue item item_id=%s youtube_id=%s karaoke=%s burn_lyrics=%s",
                item.id,
                item.media.youtube_id,
                item.requested_karaoke,
                item.requested_burn_lyrics,
            )
            # Update status to downloading
            await self.queue_service.update_status_async(
                db, item_id, QueueStatus.DOWNLOADING
            )

            if item.requested_karaoke:
                if existing_media_path and existing_vocals_path:
                    logger.info(
                        "Reusing existing karaoke media item_id=%s media=%s",
                        item.id,
                        existing_media_path,
                    )
                    await self.queue_service.update_status_async(
                        db, item_id, QueueStatus.READY
                    )
                    return
                demucs_health = self.demucs_client.health_check()
                if not demucs_health.healthy:
                    logger.warning(
                        "Demucs unhealthy for item_id=%s api_url=%s detail=%s",
                        item_id,
                        demucs_health.api_url,
                        demucs_health.detail,
                    )
                    await self.queue_service.update_status_async(
                        db,
                        item_id,
                        QueueStatus.FAILED,
                        error=(
                            f"Demucs unavailable at {demucs_health.api_url}: "
                            f"{demucs_health.detail}"
                        ),
                    )
                    return
                if existing_media_path:
                    logger.info(
                        "Reusing existing media for karaoke item_id=%s media=%s",
                        item.id,
                        existing_media_path,
                    )
                    extracted_audio_path = (
                        settings.cache_path
                        / "audio"
                        / f"{item.media.youtube_id}.wav"
                    )
                    audio_path = await asyncio.to_thread(
                        self.ffmpeg.extract_audio,
                        existing_media_path,
                        extracted_audio_path,
                    )
                    video_path = existing_media_path
                else:
                    # Karaoke flow prefers separate tracks for processing.
                    video_path = await asyncio.to_thread(
                        self.youtube_service.download_video, item.media.youtube_id
                    )
                    # Download audio only for karaoke flow
                    audio_path = await asyncio.to_thread(
                        self.youtube_service.download_audio, item.media.youtube_id
                    )
                # Karaoke flow
                await self._process_karaoke(db, item, video_path, audio_path)
            else:
                if existing_media_path:
                    logger.info(
                        "Reusing existing media for non-karaoke item_id=%s media=%s",
                        item.id,
                        existing_media_path,
                    )
                    await self.queue_service.update_status_async(
                        db, item_id, QueueStatus.READY
                    )
                    return
                # Non-karaoke flow: prefer single file with built-in audio.
                video_path = await asyncio.to_thread(
                    self.youtube_service.download_video_with_audio, item.media.youtube_id
                )
                self.queue_service.set_media_path(db, item_id, str(video_path))
                await self.queue_service.update_status_async(
                    db, item_id, QueueStatus.READY
                )
                logger.info("Non-karaoke processing completed item_id=%s output=%s", item_id, video_path)

        except Exception as e:
            logger.exception("Failed processing queue item %s", item_id)
            await self.queue_service.update_status_async(
                db, item_id, QueueStatus.FAILED, error=str(e)
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

    async def _process_karaoke(
        self, db: Session, item, video_path: Path, audio_path: Path
    ):
        """
        Process karaoke-specific flow.

        Args:
            db: Database session
            item: Queue item
            video_path: Path to video file
            audio_path: Path to audio file
        """
        # Update status to processing
        await self.queue_service.update_status_async(
            db, item.id, QueueStatus.PROCESSING
        )

        # Remove vocals using Demucs
        demucs_response = await self.demucs_client.separate_vocals(audio_path)
        no_vocals_path = Path(demucs_response.no_vocals_path)
        logger.info(
            "Demucs separation completed item_id=%s no_vocals=%s",
            item.id,
            no_vocals_path,
        )
        self.queue_service.set_vocals_path(db, item.id, str(no_vocals_path))

        output_path = settings.cache_path / f"{item.media.youtube_id}_karaoke.mp4"
        if item.requested_burn_lyrics:
            lyrics = await self.lyrics_service.fetch_lyrics(item.media.title, item.media.artist)
            if lyrics:
                lyrics_dir = settings.cache_path / "lyrics"
                lyrics_dir.mkdir(parents=True, exist_ok=True)
                lyrics_path = lyrics_dir / f"{item.media.youtube_id}.lrc"
                lyrics_path.write_text(lyrics, encoding="utf-8")
                self.queue_service.set_lyrics_path(db, item.id, str(lyrics_path))
            await asyncio.to_thread(
                self.ffmpeg.burn_subtitles,
                video_path=video_path,
                audio_path=no_vocals_path,
                subtitle_text=lyrics or "No lyrics available",
                output_path=output_path,
            )
        else:
            await asyncio.to_thread(
                self.ffmpeg.combine_audio_video,
                video_path=video_path,
                audio_path=no_vocals_path,
                output_path=output_path,
            )

        # Update item with final media path
        self.queue_service.set_media_path(db, item.id, str(output_path))
        await self.queue_service.update_status_async(db, item.id, QueueStatus.READY)
        logger.info("Karaoke processing completed item_id=%s output=%s", item.id, output_path)
