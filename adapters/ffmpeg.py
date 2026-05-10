"""FFmpeg adapter for video/audio processing."""
import subprocess
from pathlib import Path
from config import settings


class FFmpegAdapter:
    """Wrapper for ffmpeg command-line tool."""

    def __init__(self, ffmpeg_path: str = None):
        self.ffmpeg_path = ffmpeg_path or settings.ffmpeg_path

    def combine_audio_video(
        self, video_path: Path, audio_path: Path, output_path: Path
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

        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def extract_audio(self, source_path: Path, output_path: Path) -> Path:
        """Extract source audio stream without re-encoding."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-i",
            str(source_path),
            "-vn",
            "-c:a",
            "copy",
            "-y",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def extract_video_thumbnail(self, source_path: Path, output_path: Path) -> Path:
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
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def extract_embedded_thumbnail(self, source_path: Path, output_path: Path) -> Path:
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
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
