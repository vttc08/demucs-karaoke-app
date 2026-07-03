"""FFmpeg adapter for video/audio processing."""
import asyncio
import json
import math
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
        audio_codec: str | None = None,
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
        codec = (audio_codec if audio_codec is not None else settings.ffmpeg_audio_codec)
        codec = (codec or "").strip().lower()
        if codec == "aac":
            audio_args = ["-c:a", "aac", "-b:a", "192k"]
        else:
            audio_args = ["-c:a", "copy"]
        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            *audio_args,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-y",
            str(output_path),
        ]

        self._run_command(cmd, cancel_event=cancel_event)
        return output_path

    def transcode_cdg_to_mp4(
        self,
        cdg_path: Path,
        audio_path: Path,
        output_path: Path,
        *,
        audio_codec: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Render CDG graphics and pair them with audio into an MP4 container."""
        codec = (audio_codec if audio_codec is not None else settings.ffmpeg_audio_codec)
        codec = (codec or "").strip().lower()
        if codec == "aac":
            audio_args = ["-c:a", "aac", "-b:a", "192k"]
        else:
            audio_args = ["-c:a", "copy"]
        cmd = [
            self.ffmpeg_path,
            "-copyts",
            "-i",
            str(cdg_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-tune",
            "stillimage",
            *audio_args,
            "-shortest",
        ]
        cmd.extend(["-movflags", "+faststart", "-y", str(output_path)])
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
            self.ffprobe_path,
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

    def has_audio_stream(self, source_path: Path) -> bool:
        """Return whether the source file exposes at least one audio stream."""
        probe_cmd = [
            self.ffprobe_path,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-select_streams",
            "a",
            str(source_path),
        ]
        try:
            result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout or "{}")
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
            return False

        streams = payload.get("streams") if isinstance(payload, dict) else []
        return isinstance(streams, list) and bool(streams)

    @property
    def ffprobe_path(self) -> str:
        """Resolve ffprobe next to a configured ffmpeg binary when possible."""
        ffmpeg_path = Path(self.ffmpeg_path)
        if ffmpeg_path.name.lower() in {"ffmpeg", "ffmpeg.exe"}:
            sibling_name = (
                "ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe"
            )
            if ffmpeg_path.parent != Path("."):
                return str(ffmpeg_path.with_name(sibling_name))
        return "ffprobe"

    def probe_media(self, source_path: Path) -> dict[str, object]:
        """Return duration, start time, and stream presence for a media file."""
        cmd = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration,start_time:stream=codec_type,avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            str(source_path),
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout or "{}")
        format_data = payload.get("format") if isinstance(payload, dict) else {}
        streams = payload.get("streams") if isinstance(payload, dict) else []
        if not isinstance(format_data, dict):
            format_data = {}
        if not isinstance(streams, list):
            streams = []

        duration = self._finite_float(format_data.get("duration"))
        start_time = self._finite_float(format_data.get("start_time")) or 0.0
        if duration is None or duration <= 0:
            raise ValueError(f"Unable to determine media duration: {source_path}")

        stream_types = {
            str(stream.get("codec_type"))
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type")
        }
        frame_rates = [
            self._parse_frame_rate(stream)
            for stream in streams
            if isinstance(stream, dict) and str(stream.get("codec_type")) == "video"
        ]
        frame_rate = next((rate for rate in frame_rates if rate is not None), None)
        return {
            "duration": duration,
            "start_time": start_time,
            "has_video": "video" in stream_types,
            "has_audio": "audio" in stream_types,
            "frame_rate": frame_rate,
        }

    def get_video_keyframes(self, source_path: Path) -> list[float]:
        """Return browser-timeline keyframe timestamps for the first video stream."""
        media = self.probe_media(source_path)
        if not media["has_video"]:
            return []

        cmd = [
            self.ffprobe_path,
            "-v",
            "error",
            "-skip_frame",
            "nokey",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp_time,pts_time",
            "-of",
            "json",
            str(source_path),
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout or "{}")
        frames = payload.get("frames") if isinstance(payload, dict) else []
        if not isinstance(frames, list):
            frames = []

        start_time = float(media["start_time"])
        duration = float(media["duration"])
        timestamps: set[float] = {0.0}
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            raw = frame.get("best_effort_timestamp_time") or frame.get("pts_time")
            timestamp = self._finite_float(raw)
            if timestamp is None:
                continue
            normalized = min(duration, max(0.0, timestamp - start_time))
            timestamps.add(round(normalized, 6))
        return sorted(timestamps)

    def lossless_trim(
        self,
        source_path: Path,
        output_path: Path,
        start_time: float,
        end_time: float,
    ) -> Path:
        """Copy all known streams into a trimmed file without re-encoding."""
        if end_time <= start_time:
            raise ValueError("Trim end must be after trim start")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-ss",
            f"{start_time:.6f}",
            "-i",
            str(source_path),
            "-t",
            f"{end_time - start_time:.6f}",
            "-map",
            "0",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
        ]
        if output_path.suffix.lower() in {".mp4", ".m4v", ".mov"}:
            cmd.extend(["-movflags", "+faststart"])
        cmd.extend(["-y", str(output_path)])
        self._run_command(cmd)
        return output_path

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
            self.ffprobe_path,
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
    def _finite_float(value: object) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    @staticmethod
    def _parse_frame_rate(stream: object) -> float | None:
        if not isinstance(stream, dict):
            return None
        for key in ("avg_frame_rate", "r_frame_rate"):
            raw = stream.get(key)
            if not isinstance(raw, str) or not raw.strip() or raw == "0/0":
                continue
            if "/" in raw:
                numerator_raw, denominator_raw = raw.split("/", 1)
                numerator = FFmpegAdapter._finite_float(numerator_raw)
                denominator = FFmpegAdapter._finite_float(denominator_raw)
                if numerator is None or denominator in (None, 0):
                    continue
                frame_rate = numerator / denominator
            else:
                frame_rate = FFmpegAdapter._finite_float(raw)
            if frame_rate is not None and math.isfinite(frame_rate) and frame_rate > 0:
                return frame_rate
        return None

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
