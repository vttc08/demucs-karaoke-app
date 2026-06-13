"""FFmpeg adapter for video/audio processing."""
import asyncio
import subprocess
import threading
import time
from pathlib import Path
from config import settings


class FFmpegAdapter:
    """Wrapper for ffmpeg command-line tool."""

    def __init__(self, ffmpeg_path: str = None):
        self.ffmpeg_path = ffmpeg_path or settings.ffmpeg_path

    def combine_audio_video(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """
        Combine video and audio files.

        Args:
            video_path: Path to video file
            audio_path: Path to audio file
            output_path: Path for output file

        Returns:
            Path to output file
        """
        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-y",
            str(output_path),
        ]

        self._run_command(cmd, cancel_event=cancel_event)
        return output_path

    def extract_audio(
        self,
        source_path: Path,
        output_path: Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Extract source audio stream, copying when the codec is container-safe."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        source_codec = self._probe_audio_codec(source_path)
        copy_safe_codecs = {"aac", "alac"}
        if source_codec in copy_safe_codecs:
            codec_args = ["-c:a", "copy"]
        else:
            codec_args = ["-c:a", "aac", "-b:a", "192k"]
        cmd = [
            self.ffmpeg_path,
            "-i",
            str(source_path),
            "-vn",
            *codec_args,
            "-y",
            str(output_path),
        ]
        self._run_command(cmd, cancel_event=cancel_event)
        return output_path

    def extract_video_thumbnail(
        self,
        source_path: Path,
        output_path: Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Extract a single frame thumbnail from a video file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-ss",
            "00:00:01",
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=512:-1:force_original_aspect_ratio=decrease",
            "-q:v",
            "2",
            "-y",
            str(output_path),
        ]
        self._run_command(cmd, cancel_event=cancel_event)
        return output_path

    def extract_embedded_thumbnail(
        self,
        source_path: Path,
        output_path: Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Extract embedded cover art from a media file when available."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-vf",
            "scale=512:-1:force_original_aspect_ratio=decrease",
            "-q:v",
            "2",
            "-y",
            str(output_path),
        ]
        self._run_command(cmd, cancel_event=cancel_event)
        return output_path

    def has_video_stream(self, source_path: Path) -> bool:
        """Return whether the source file exposes at least one video stream."""
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(source_path),
        ]
        try:
            result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
        return bool((result.stdout or "").strip())

    def _run_command(self, cmd: list[str], *, cancel_event: threading.Event | None = None) -> None:
        if cancel_event is None:
            subprocess.run(cmd, check=True, capture_output=True)
            return

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            while True:
                if cancel_event.is_set():
                    self._terminate_process(process)
                    raise asyncio.CancelledError()
                return_code = process.poll()
                if return_code is not None:
                    stdout, stderr = process.communicate()
                    if return_code != 0:
                        raise subprocess.CalledProcessError(
                            returncode=return_code,
                            cmd=cmd,
                            output=stdout,
                            stderr=stderr,
                        )
                    return
                time.sleep(0.1)
        except asyncio.CancelledError:
            self._terminate_process(process)
            raise
        except Exception:
            self._terminate_process(process)
            raise

    def _probe_audio_codec(self, source_path: Path) -> str | None:
        """Return the first audio codec name for a local source file when available."""
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ]
        try:
            result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        codec = (result.stdout or "").strip().lower()
        return codec or None

    @staticmethod
    def _terminate_process(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        except ProcessLookupError:
            return
