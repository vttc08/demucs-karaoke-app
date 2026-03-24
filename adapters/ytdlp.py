"""yt-dlp adapter for YouTube downloads and search."""
import subprocess
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Iterable, Tuple, Optional
from config import settings

logger = logging.getLogger(__name__)


class YtDlpAdapter:
    """Wrapper for yt-dlp command-line tool."""

    def __init__(self, ytdlp_path: str = None):
        self.ytdlp_path = ytdlp_path or settings.ytdlp_path
        logger.info(f"YtDlpAdapter initialized with path: {self.ytdlp_path}")

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search YouTube for videos.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            List of video metadata dictionaries
            
        Raises:
            RuntimeError: If search fails
        """
        cmd = [
            self.ytdlp_path,
            f"ytsearch{max_results}:{query}",
            "--dump-json",
            "--skip-download",
            "--flat-playlist",
            "--extractor-args",
            "youtube:player_client=web",
            "--no-playlist",
            "--no-warnings",
        ]

        logger.info(f"Executing YouTube search: {query}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30  # 30 second timeout
            )
        except subprocess.TimeoutExpired:
            logger.error(f"YouTube search timed out for query: {query}")
            raise RuntimeError("YouTube search timed out. Please try again.")
        except subprocess.CalledProcessError as e:
            logger.error(f"YouTube search failed: {e.stderr}")
            raise RuntimeError(f"YouTube search failed: {e.stderr[:200]}")
        except FileNotFoundError:
            logger.error(f"yt-dlp not found at: {self.ytdlp_path}")
            raise RuntimeError(f"yt-dlp not found. Please install it: pip install yt-dlp")
        except Exception as e:
            logger.error(f"Unexpected error during search: {str(e)}")
            raise RuntimeError(f"Search failed: {str(e)}")

        # yt-dlp outputs one JSON object per line for search results
        videos = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    video_data = json.loads(line)
                    videos.append(
                        {
                            "video_id": video_data.get("id"),
                            "title": video_data.get("title"),
                            "channel": video_data.get("uploader", video_data.get("channel")),
                            "duration": video_data.get("duration_string"),
                            "thumbnail": video_data.get("thumbnail"),
                        }
                    )
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse search result line: {line[:100]}")
                    continue
        
        logger.info(f"Search returned {len(videos)} results for query: {query}")
        return videos

    def download_audio(self, youtube_id: str, output_dir: Path) -> Path:
        """
        Download audio from YouTube video.

        Args:
            youtube_id: YouTube video ID
            output_dir: Directory to save audio file

        Returns:
            Path to downloaded audio file
            
        Raises:
            RuntimeError: If download fails
        """
        output_template = str(output_dir / f"{youtube_id}.%(ext)s")
        attempts = [
            ("bestaudio[ext=m4a]/bestaudio/best", "web", False, True),
            ("bestaudio/best", "web", False, True),
            (None, "web", False, True),
            (None, None, False, False),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            attempts=attempts,
            extensions=[".wav", ".m4a", ".webm", ".mp3", ".opus", ".mp4", ".mkv"],
            media_type="audio",
        )

    def download_video(self, youtube_id: str, output_dir: Path) -> Path:
        """
        Download video from YouTube.

        Args:
            youtube_id: YouTube video ID
            output_dir: Directory to save video file

        Returns:
            Path to downloaded video file
            
        Raises:
            RuntimeError: If download fails
        """
        output_template = str(output_dir / f"{youtube_id}.%(ext)s")
        # Karaoke flow only needs a video track; avoid merge-heavy selectors.
        attempts = [
            ("bestvideo[ext=mp4]/best[ext=mp4]/bestvideo/best", "web", False, True),
            ("bestvideo/best", "web", False, True),
            ("bestvideo/best", None, False, False),
            (None, None, False, False),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            attempts=attempts,
            extensions=[".mp4", ".mkv", ".webm"],
            media_type="video",
        )

    def download_video_with_audio(self, youtube_id: str, output_dir: Path) -> Path:
        """
        Download a progressive video that already includes audio.

        Args:
            youtube_id: YouTube video ID
            output_dir: Directory to save video file

        Returns:
            Path to downloaded video file

        Raises:
            RuntimeError: If download fails
        """
        output_template = str(output_dir / f"{youtube_id}.%(ext)s")
        attempts = [
            ("best[ext=mp4]/best", "web", False, True),
            ("best", "web", False, True),
            (None, "web", False, True),
            (None, None, False, False),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            attempts=attempts,
            extensions=[".mp4", ".mkv", ".webm"],
            media_type="progressive video+audio",
        )

    def _download_with_attempts(
        self,
        youtube_id: str,
        output_dir: Path,
        output_template: str,
        attempts: Iterable[Tuple[Optional[str], Optional[str], bool, bool]],
        extensions: List[str],
        media_type: str,
    ) -> Path:
        """Run yt-dlp download attempts with format/client fallbacks."""
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        last_error = "unknown failure"

        logger.info(f"Downloading {media_type} for: {youtube_id}")
        for fmt, client, merge_mp4, use_extractor_args in attempts:
            cmd = [
                self.ytdlp_path,
                url,
                "-o",
                output_template,
                "--no-playlist",
            ]
            if fmt:
                cmd[2:2] = ["-f", fmt]
            if use_extractor_args and client:
                cmd[2:2] = ["--extractor-args", f"youtube:player_client={client}"]
            if merge_mp4:
                cmd.extend(["--merge-output-format", "mp4"])

            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=300)
                output_path = self._find_downloaded_file(output_dir, youtube_id, extensions)
                if not output_path.exists():
                    last_error = f"file not found: {output_path}"
                    logger.warning(
                        "Download attempt succeeded but output missing (%s, client=%s)",
                        fmt or "<default>",
                        client or "<default>",
                    )
                    continue
                logger.info(
                    "%s downloaded successfully: %s (format=%s, client=%s)",
                    media_type.capitalize(),
                    output_path,
                    fmt or "<default>",
                    client or "<default>",
                )
                return output_path
            except subprocess.TimeoutExpired:
                last_error = "Download timed out"
                logger.warning(
                    "%s download attempt timed out (%s, client=%s)",
                    media_type.capitalize(),
                    fmt or "<default>",
                    client or "<default>",
                )
            except subprocess.CalledProcessError as e:
                stderr = self._decode_stderr(e.stderr)
                last_error = self._extract_relevant_error(stderr, e.returncode)
                logger.warning(
                    "%s download attempt failed (%s, client=%s): %s",
                    media_type.capitalize(),
                    fmt or "<default>",
                    client or "<default>",
                    last_error,
                )

        logger.error(
            "%s download failed for %s after fallback attempts: %s",
            media_type.capitalize(),
            youtube_id,
            last_error,
        )
        raise RuntimeError(f"Download failed: {last_error}")

    def _find_downloaded_file(self, output_dir: Path, youtube_id: str, extensions: List[str]) -> Path:
        """
        Find downloaded file, supporting yt-dlp's format-suffixed output names.
        """
        exact_candidates = [output_dir / f"{youtube_id}{ext}" for ext in extensions]
        for candidate in exact_candidates:
            if candidate.exists():
                return candidate

        # yt-dlp can produce names like <id>.f299.mp4 when streams are not merged.
        for ext in extensions:
            matches = sorted(output_dir.glob(f"{youtube_id}*{ext}"))
            if matches:
                return matches[0]

        # Return primary expected path for clearer error messages upstream.
        return exact_candidates[0]

    @staticmethod
    def _decode_stderr(stderr: Any) -> str:
        if isinstance(stderr, bytes):
            return stderr.decode(errors="ignore")
        return str(stderr or "")

    @staticmethod
    def _extract_relevant_error(stderr: str, return_code: int) -> str:
        if not stderr:
            return f"yt-dlp exited {return_code}"
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        error_lines = [line for line in lines if line.startswith("ERROR:")]
        if error_lines:
            return error_lines[-1][:200]
        warning_lines = [line for line in lines if line.startswith("WARNING:")]
        if warning_lines:
            return warning_lines[-1][:200]
        return lines[-1][:200]
