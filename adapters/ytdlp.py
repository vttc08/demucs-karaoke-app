"""yt-dlp adapter for YouTube downloads and search."""
import asyncio
import json
import logging
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Iterable, Tuple, Optional, Callable
from config import settings

logger = logging.getLogger(__name__)
_DOWNLOAD_PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_STRUCTURED_PROGRESS_RE = re.compile(r"\[download\]\[karaoke-progress\]\s+(\d+(?:\.\d+)?)")
_STREAM_DONE = object()


class YtDlpAdapter:
    """Wrapper for yt-dlp command-line tool."""

    def __init__(self, ytdlp_path: str = None):
        self.ytdlp_path = ytdlp_path or settings.ytdlp_path
        logger.info("YtDlpAdapter initialized ytdlp_path=%s", self.ytdlp_path)

    @staticmethod
    def _proxy_args() -> List[str]:
        """Build proxy arguments for yt-dlp command if configured."""
        if settings.ytdlp_proxy_url:
            return ["--proxy", settings.ytdlp_proxy_url]
        return []

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
        cmd.extend(self._proxy_args())

        logger.info("Executing YouTube search query=%r max_results=%s", query, max_results)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30  # 30 second timeout
            )
        except subprocess.TimeoutExpired:
            logger.error("YouTube search timed out query=%r", query)
            raise RuntimeError("YouTube search timed out. Please try again.")
        except subprocess.CalledProcessError as e:
            logger.error("YouTube search failed query=%r stderr=%s", query, e.stderr)
            raise RuntimeError(f"YouTube search failed: {e.stderr[:200]}")
        except FileNotFoundError:
            logger.error("yt-dlp not found path=%s", self.ytdlp_path)
            raise RuntimeError(f"yt-dlp not found. Please install it: pip install yt-dlp")
        except Exception as e:
            logger.exception("Unexpected error during search query=%r error=%s", query, str(e))
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
                    logger.warning("Failed to parse search result line prefix=%r", line[:100])
                    continue

        logger.info("YouTube search completed query=%r result_count=%s", query, len(videos))
        return videos

    def get_video_info(self, video_url: str) -> Dict[str, Any]:
        """
        Fetch metadata for a single YouTube video URL.

        Args:
            video_url: Full YouTube URL

        Returns:
            Video metadata dictionary

        Raises:
            RuntimeError: If metadata fetch fails
        """
        attempts = [
            ("web", True),
            (None, False),
        ]
        logger.info("Fetching YouTube metadata url=%r", video_url)
        last_error = "unknown metadata failure"
        video_data = None

        for idx, (client, use_extractor_args) in enumerate(attempts):
            cmd = [
                self.ytdlp_path,
                video_url,
                "--dump-single-json",
                "--skip-download",
                "--no-playlist",
                "--no-warnings",
            ]
            if use_extractor_args and client:
                cmd[2:2] = ["--extractor-args", f"youtube:player_client={client}"]
            cmd.extend(self._proxy_args())
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                video_data = json.loads((result.stdout or "").strip())
                break
            except subprocess.TimeoutExpired:
                logger.error("YouTube metadata fetch timed out url=%r", video_url)
                raise RuntimeError("YouTube metadata fetch timed out. Please try again.")
            except subprocess.CalledProcessError as e:
                stderr = self._decode_stderr(e.stderr)
                last_error = self._extract_relevant_error(stderr, e.returncode)
                remaining = len(attempts) - (idx + 1)
                if remaining > 0 and "Requested format is not available" in last_error:
                    logger.info(
                        "Metadata fallback: format unavailable (client=%s), trying next strategy",
                        client or "<default>",
                    )
                elif remaining > 0:
                    logger.info(
                        "Metadata fallback: attempt failed (client=%s), trying next strategy",
                        client or "<default>",
                    )
                else:
                    logger.error(
                        "YouTube metadata fetch failed url=%r client=%s error=%s",
                        video_url,
                        client or "<default>",
                        last_error,
                    )
            except FileNotFoundError:
                logger.error("yt-dlp not found path=%s", self.ytdlp_path)
                raise RuntimeError("yt-dlp not found. Please install it: pip install yt-dlp")
            except json.JSONDecodeError:
                last_error = "Invalid yt-dlp metadata response"
                logger.error(
                    "Failed to decode yt-dlp single json url=%r client=%s",
                    video_url,
                    client or "<default>",
                )

        if not video_data:
            raise RuntimeError(f"YouTube metadata fetch failed: {last_error[:200]}")

        return {
            "video_id": video_data.get("id"),
            "title": video_data.get("title"),
            "channel": video_data.get("uploader", video_data.get("channel")),
            "duration": video_data.get("duration_string"),
            "thumbnail": video_data.get("thumbnail"),
        }

    def download_audio(
        self,
        youtube_id: str,
        output_dir: Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Path:
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
        output_stem = f"{youtube_id}.audio"
        output_template = str(output_dir / f"{output_stem}.%(ext)s")
        attempts = [
            (None, None, False, False),
            ("bestaudio[ext=m4a]/bestaudio/best", "web", False, True),
            ("bestaudio/best", "web", False, True),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            output_stem=output_stem,
            attempts=attempts,
            extensions=[".wav", ".m4a", ".webm", ".mp3", ".opus", ".mp4", ".mkv"],
            media_type="audio",
            cancel_event=cancel_event,
        )

    def download_audio_with_progress(
        self,
        youtube_id: str,
        output_dir: Path,
        *,
        progress_callback: Callable[[int, str], None] | None = None,
        log_callback: Callable[[str, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Download audio while streaming progress and log lines."""
        output_stem = f"{youtube_id}.audio"
        output_template = str(output_dir / f"{output_stem}.%(ext)s")
        attempts = [
            (None, None, False, False),
            ("bestaudio[ext=m4a]/bestaudio/best", "web", False, True),
            ("bestaudio/best", "web", False, True),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            output_stem=output_stem,
            attempts=attempts,
            extensions=[".wav", ".m4a", ".webm", ".mp3", ".opus", ".mp4", ".mkv"],
            media_type="audio",
            progress_callback=progress_callback,
            log_callback=log_callback,
            cancel_event=cancel_event,
        )

    def download_video(
        self,
        youtube_id: str,
        output_dir: Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Path:
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
            (None, None, False, False),
            ("bestvideo/best", None, False, False),
            ("bestvideo[ext=mp4]/best[ext=mp4]/bestvideo/best", "web", False, True),
            ("bestvideo/best", "web", False, True),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            output_stem=youtube_id,
            attempts=attempts,
            extensions=[".mp4", ".mkv", ".webm"],
            media_type="video",
            cancel_event=cancel_event,
        )

    def download_video_with_progress(
        self,
        youtube_id: str,
        output_dir: Path,
        *,
        progress_callback: Callable[[int, str], None] | None = None,
        log_callback: Callable[[str, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Download video while streaming progress and log lines."""
        output_template = str(output_dir / f"{youtube_id}.%(ext)s")
        attempts = [
            (None, None, False, False),
            ("bestvideo/best", None, False, False),
            ("bestvideo[ext=mp4]/best[ext=mp4]/bestvideo/best", "web", False, True),
            ("bestvideo/best", "web", False, True),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            output_stem=youtube_id,
            attempts=attempts,
            extensions=[".mp4", ".mkv", ".webm"],
            media_type="video",
            progress_callback=progress_callback,
            log_callback=log_callback,
            cancel_event=cancel_event,
        )

    def download_video_with_audio(
        self,
        youtube_id: str,
        output_dir: Path,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Path:
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
            (None, None, False, False),
            ("best[ext=mp4]/best", "web", False, True),
            ("best", "web", False, True),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            output_stem=youtube_id,
            attempts=attempts,
            extensions=[".mp4", ".mkv", ".webm"],
            media_type="progressive video+audio",
            cancel_event=cancel_event,
        )

    def download_video_with_audio_progress(
        self,
        youtube_id: str,
        output_dir: Path,
        *,
        progress_callback: Callable[[int, str], None] | None = None,
        log_callback: Callable[[str, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Download progressive video while streaming progress and log lines."""
        output_template = str(output_dir / f"{youtube_id}.%(ext)s")
        attempts = [
            (None, None, False, False),
            ("best[ext=mp4]/best", "web", False, True),
            ("best", "web", False, True),
        ]
        return self._download_with_attempts(
            youtube_id=youtube_id,
            output_dir=output_dir,
            output_template=output_template,
            output_stem=youtube_id,
            attempts=attempts,
            extensions=[".mp4", ".mkv", ".webm"],
            media_type="progressive video+audio",
            progress_callback=progress_callback,
            log_callback=log_callback,
            cancel_event=cancel_event,
        )

    def _download_with_attempts(
        self,
        youtube_id: str,
        output_dir: Path,
        output_template: str,
        output_stem: str,
        attempts: Iterable[Tuple[Optional[str], Optional[str], bool, bool]],
        extensions: List[str],
        media_type: str,
        progress_callback: Callable[[int, str], None] | None = None,
        log_callback: Callable[[str, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        """Run yt-dlp download attempts with format/client fallbacks."""
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        last_error = "unknown failure"
        attempt_list = list(attempts)

        logger.info("Downloading media_type=%s youtube_id=%s", media_type, youtube_id)
        for idx, (fmt, client, merge_mp4, use_extractor_args) in enumerate(attempt_list):
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
            if progress_callback or log_callback or cancel_event is not None:
                # yt-dlp writes progress updates with carriage returns by default,
                # which line-based readers only see after the process exits.
                cmd.extend(
                    [
                        "--newline",
                        "--progress",
                        "--no-colors",
                        "--progress-template",
                        "download:[download][karaoke-progress] %(progress._percent)f",
                    ]
                )
            cmd.extend(self._proxy_args())

            try:
                if progress_callback or log_callback or cancel_event is not None:
                    self._run_streaming_download(
                        cmd,
                        progress_callback=progress_callback,
                        log_callback=log_callback,
                        cancel_event=cancel_event,
                    )
                else:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
                output_path = self._find_downloaded_file(output_dir, output_stem, extensions)
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
                remaining = len(attempt_list) - (idx + 1)
                if (
                    remaining > 0
                    and "Requested format is not available" in last_error
                ):
                    logger.info(
                        "%s fallback: format unavailable (%s, client=%s), trying next strategy",
                        media_type.capitalize(),
                        fmt or "<default>",
                        client or "<default>",
                    )
                else:
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

    def _run_streaming_download(
        self,
        cmd: list[str],
        *,
        progress_callback: Callable[[int, str], None] | None = None,
        log_callback: Callable[[str, str], None] | None = None,
        timeout_seconds: float = 300,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Run a yt-dlp download command and stream stdout/stderr lines."""
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        stdout_lines: list[str] = []
        line_queue: queue.Queue[object] = queue.Queue()
        reader_thread: threading.Thread | None = None
        deadline = time.monotonic() + timeout_seconds

        def enqueue_stdout(stream) -> None:
            try:
                while True:
                    line = stream.readline()
                    if line == "":
                        break
                    line_queue.put(line)
            finally:
                line_queue.put(_STREAM_DONE)

        if process.stdout is not None:
            reader_thread = threading.Thread(
                target=enqueue_stdout,
                args=(process.stdout,),
                daemon=True,
                name="yt-dlp-stream-reader",
            )
            reader_thread.start()

        try:
            if reader_thread is not None:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise asyncio.CancelledError()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(cmd, timeout_seconds, output="\n".join(stdout_lines))
                    try:
                        item = line_queue.get(timeout=min(0.1, max(remaining, 0.0)))
                    except queue.Empty as exc:
                        continue
                    if item is _STREAM_DONE:
                        break
                    line = str(item).rstrip()
                    if not line:
                        continue
                    stdout_lines.append(line)
                    match = self._parse_progress_line(line)
                    if match is not None:
                        if progress_callback:
                            progress_callback(match, line)
                        continue
                    if log_callback:
                        stream_name = "stderr" if line.startswith(("ERROR:", "WARNING:")) else "stdout"
                        log_callback(stream_name, line)

            remaining = max(0.0, deadline - time.monotonic())
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise asyncio.CancelledError()
                return_code = process.poll()
                if return_code is not None:
                    break
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(cmd, timeout_seconds, output="\n".join(stdout_lines))
                try:
                    return_code = process.wait(timeout=min(0.1, remaining))
                except subprocess.TimeoutExpired:
                    return_code = None
                if return_code is not None:
                    break
                remaining = max(0.0, deadline - time.monotonic())
            if return_code != 0:
                stderr = "\n".join(stdout_lines)
                raise subprocess.CalledProcessError(
                    returncode=return_code,
                    cmd=cmd,
                    stderr=stderr,
                    output="\n".join(stdout_lines),
                )
        except asyncio.CancelledError:
            self._terminate_process(process)
            raise
        except Exception:
            self._terminate_process(process)
            raise
        finally:
            if process.stdout is not None:
                process.stdout.close()
            if reader_thread is not None:
                reader_thread.join(timeout=1)

    @staticmethod
    def _terminate_process(process: subprocess.Popen) -> None:
        """Terminate a child process and escalate to kill if it ignores SIGTERM."""
        if process.poll() is not None:
            return
        try:
            terminate = getattr(process, "terminate", None)
            if terminate is not None:
                terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kill = getattr(process, "kill", None)
            if kill is not None:
                kill()
            process.wait(timeout=5)
        except ProcessLookupError:
            return

    def _find_downloaded_file(self, output_dir: Path, output_stem: str, extensions: List[str]) -> Path:
        """
        Find downloaded file, supporting yt-dlp's format-suffixed output names.
        """
        exact_candidates = [output_dir / f"{output_stem}{ext}" for ext in extensions]
        for candidate in exact_candidates:
            if candidate.exists():
                return candidate

        # yt-dlp can produce names like <stem>.f299.mp4 when streams are not merged.
        for ext in extensions:
            matches = sorted(output_dir.glob(f"{output_stem}*{ext}"))
            if matches:
                return matches[0]

        # Return primary expected path for clearer error messages upstream.
        return exact_candidates[0]

    @staticmethod
    def _parse_progress_line(line: str) -> int | None:
        """Return parsed yt-dlp progress percent from a console line."""
        structured_match = _STRUCTURED_PROGRESS_RE.search(line)
        if structured_match:
            return max(0, min(100, int(float(structured_match.group(1)))))

        fallback_match = _DOWNLOAD_PROGRESS_RE.search(line)
        if fallback_match:
            return max(0, min(100, int(float(fallback_match.group(1)))))

        return None

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
