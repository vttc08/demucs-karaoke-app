"""FFmpeg adapter for video/audio processing."""
import subprocess
import re
from pathlib import Path
from typing import Optional
from config import settings


class FFmpegAdapter:
    """Wrapper for ffmpeg command-line tool."""

    def __init__(self, ffmpeg_path: str = None):
        self.ffmpeg_path = ffmpeg_path or settings.ffmpeg_path
        self.ffmpeg_preset = settings.ffmpeg_preset
        self.ffmpeg_crf = settings.ffmpeg_crf

    def burn_subtitles(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_text: str,
        output_path: Path,
        font_size: int = 24,
    ) -> Path:
        """
        Create video with burned-in subtitles.

        Args:
            video_path: Path to input video
            audio_path: Path to audio (e.g., vocals-removed version)
            subtitle_text: Subtitle content (SRT format or simple text)
            output_path: Path for output video
            font_size: Font size for subtitles

        Returns:
            Path to output video file
        """
        # For MVP, we'll create a simple subtitle file
        srt_path = output_path.parent / f"{output_path.stem}.srt"
        self._create_srt_file(subtitle_text, srt_path)

        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-i", str(audio_path),
            "-vf", f"subtitles={srt_path}:force_style='FontSize={font_size}'",
            "-map", "0:v:0",  # Video from first input
            "-map", "1:a:0",  # Audio from second input
            "-c:v", "libx264",
            "-preset", self.ffmpeg_preset,
            "-crf", str(self.ffmpeg_crf),
            "-c:a", "aac",
            "-shortest",
            "-y",  # Overwrite output
            str(output_path),
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

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
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-y",
            str(output_path),
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def extract_audio(self, source_path: Path, output_path: Path) -> Path:
        """Extract a WAV audio track from a local media file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-i",
            str(source_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-y",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def _create_srt_file(self, lyrics: str, output_path: Path):
        """Create a simple SRT subtitle file from lyrics."""
        lrc_entries = self._parse_lrc(lyrics)

        with open(output_path, "w", encoding="utf-8") as f:
            if lrc_entries:
                for i, (start_time, line) in enumerate(lrc_entries, start=1):
                    if i < len(lrc_entries):
                        end_time = lrc_entries[i][0]
                    else:
                        end_time = start_time + 5.0
                    f.write(f"{i}\n")
                    f.write(
                        f"{self._format_srt_time(start_time)} --> {self._format_srt_time(end_time)}\n"
                    )
                    f.write(f"{line}\n\n")
            else:
                # Fallback: simple line-by-line subtitles with 5-second intervals
                lines = [line.strip() for line in lyrics.split("\n") if line.strip()]
                for i, line in enumerate(lines, start=1):
                    start_time = (i - 1) * 5
                    end_time = i * 5
                    f.write(f"{i}\n")
                    f.write(
                        f"{self._format_srt_time(start_time)} --> {self._format_srt_time(end_time)}\n"
                    )
                    f.write(f"{line}\n\n")

    @staticmethod
    def _parse_lrc(lyrics: str) -> list[tuple[float, str]]:
        """Parse LRC text ([mm:ss.xx]Line) into ordered timestamped entries."""
        entries: list[tuple[float, str]] = []
        line_pattern = re.compile(r"\[(\d{2}):(\d{2})(?:\.(\d{1,3}))?\]")

        for raw_line in lyrics.split("\n"):
            matches = list(line_pattern.finditer(raw_line))
            if not matches:
                continue
            text = line_pattern.sub("", raw_line).strip()
            if not text:
                continue
            for match in matches:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                fraction = match.group(3) or "0"
                millis = int(fraction.ljust(3, "0")[:3])
                start = minutes * 60 + seconds + (millis / 1000.0)
                entries.append((start, text))

        entries.sort(key=lambda item: item[0])
        return entries

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
        total_ms = max(0, int(round(seconds * 1000)))
        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        secs = (total_ms % 60_000) // 1_000
        millis = total_ms % 1_000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
