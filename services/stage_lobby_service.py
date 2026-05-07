"""Resolve stage lobby playback media with deterministic fallback generation."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from config import settings
from services.queue_service import QueueService

logger = logging.getLogger(__name__)


class StageLobbyService:
    """Provide a playable lobby media URL for stage idle playback."""

    FALLBACK_FILE_NAME = "stage-lobby-fallback.mp4"
    FALLBACK_DURATION_SECONDS = 20

    def resolve_lobby_media_url(self) -> str:
        """Return configured lobby media URL or generated fallback URL."""
        configured_url = (settings.stage_lobby_media_path or "").strip()
        configured_file = self._resolve_media_url_to_file(configured_url)
        if configured_url and configured_file and configured_file.exists():
            return configured_url

        if configured_url:
            logger.warning(
                "Configured stage lobby media missing path=%s; generating fallback",
                configured_url,
            )

        fallback_path = settings.media_path / self.FALLBACK_FILE_NAME
        if not fallback_path.exists():
            try:
                self._generate_fallback_media(fallback_path)
            except Exception:
                logger.exception(
                    "Failed generating stage lobby fallback media path=%s",
                    fallback_path,
                )
                return configured_url

        return QueueService.build_media_url(fallback_path)

    @staticmethod
    def _resolve_media_url_to_file(media_url: str) -> Path | None:
        """Resolve /media or /cache URL to a local path when valid."""
        if not media_url:
            return None
        return QueueService._media_url_to_file(media_url)

    def _generate_fallback_media(self, output_path: Path) -> None:
        """Generate a one-time instructional loop video for empty-queue stage playback."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Generating stage lobby fallback media path=%s", output_path)
        cmd = [
            settings.ffmpeg_path,
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=1280x720:d={self.FALLBACK_DURATION_SECONDS}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:sample_rate=48000:duration={self.FALLBACK_DURATION_SECONDS}",
            "-vf",
            (
                "drawtext=text='Lobby loop media not configured':fontcolor=white:fontsize=42:"
                "x=(w-text_w)/2:y=(h-text_h)/2-30,"
                "drawtext=text='Open Settings and set Stage Lobby Media URL':fontcolor=white:"
                "fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2+30"
            ),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-y",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
