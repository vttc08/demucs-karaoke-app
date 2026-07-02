"""Atomic lossless trimming for media items and their timed sidecars."""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import shutil
import threading
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pylrc
import srt
from sqlalchemy.orm import Session

from adapters.ffmpeg import FFmpegAdapter
from models import (
    MediaItem,
    ProcessingTask,
    ProcessingTaskStatus,
    QueueItem,
    QueueStatus,
    utc_now,
)
from services.media_thumbnail_service import MediaThumbnailService
from services.queue_service import QueueService

logger = logging.getLogger(__name__)

_ACTIVE_TASK_STATUSES = {
    ProcessingTaskStatus.PENDING.value,
    ProcessingTaskStatus.DOWNLOADING.value,
    ProcessingTaskStatus.PROCESSING.value,
}
_TRIM_LOCKS: dict[int, threading.Lock] = {}
_TRIM_LOCKS_GUARD = threading.Lock()


class MediaTrimError(ValueError):
    """Base error for invalid or failed media trim operations."""


class MediaTrimNotFoundError(MediaTrimError):
    """Raised when the media row or local file cannot be found."""


class MediaTrimConflictError(MediaTrimError):
    """Raised when current application state makes a trim unsafe."""


class MediaTrimUnsupportedError(MediaTrimError):
    """Raised when an attached sidecar cannot be shifted safely."""


class MediaTrimService:
    """Coordinate keyframe validation and atomic in-place asset replacement."""

    def __init__(self, ffmpeg: FFmpegAdapter | None = None):
        self.ffmpeg = ffmpeg or FFmpegAdapter()
        self.queue_service = QueueService()
        self.thumbnail_service = MediaThumbnailService()

    def get_trim_info(self, db: Session, media_item_id: int) -> dict[str, object]:
        """Return media timing and sidecar information needed by the editor."""
        media_item, media_file = self._get_media_item_and_file(db, media_item_id)
        probe = self.ffmpeg.probe_media(media_file)
        keyframes = (
            self.ffmpeg.get_video_keyframes(media_file) if bool(probe["has_video"]) else []
        )
        return {
            "media_id": media_item.id,
            "title": media_item.title,
            "artist": media_item.artist,
            "media_url": media_item.media_path,
            "duration": round(float(probe["duration"]), 6),
            "has_video": bool(probe["has_video"]),
            "has_audio": bool(probe["has_audio"]),
            "frame_rate": (
                round(float(probe["frame_rate"]), 6)
                if isinstance(probe.get("frame_rate"), (int, float))
                else None
            ),
            "keyframes": keyframes,
            "vocals_path": media_item.vocals_path,
            "lyrics_path": media_item.lyrics_path,
            "lyrics_format": (
                Path(media_item.lyrics_path).suffix.lower().lstrip(".")
                if media_item.lyrics_path
                else None
            ),
        }

    def trim_media_item(
        self,
        db: Session,
        media_item_id: int,
        start_time: float,
        end_time: float,
    ) -> dict[str, object]:
        """Trim a media item and every attached synchronized sidecar."""
        requested_start = self._validate_time(start_time, "start_time")
        requested_end = self._validate_time(end_time, "end_time")
        if requested_end <= requested_start:
            raise MediaTrimError("end_time must be greater than start_time")

        lock = self._lock_for(media_item_id)
        if not lock.acquire(blocking=False):
            raise MediaTrimConflictError("A trim is already running for this media item")
        try:
            self._assert_no_conflicts(db, media_item_id)
            media_item, media_file = self._get_media_item_and_file(db, media_item_id)
            probe = self.ffmpeg.probe_media(media_file)
            duration = float(probe["duration"])
            if requested_start >= duration or requested_end > duration + 0.05:
                raise MediaTrimError("Trim range must be within the media duration")

            keyframes = (
                self.ffmpeg.get_video_keyframes(media_file)
                if bool(probe["has_video"])
                else []
            )
            resolved_start, resolved_end = self._resolve_bounds(
                requested_start,
                min(requested_end, duration),
                duration,
                keyframes,
                has_video=bool(probe["has_video"]),
            )
            if resolved_end - resolved_start < 0.01:
                raise MediaTrimError("Resolved trim range is empty")

            assets = self._collect_assets(media_item, media_file)
            staged: dict[Path, Path] = {}
            staged_candidates: list[Path] = []
            token = uuid.uuid4().hex
            try:
                for kind, source in assets:
                    staged_path = source.with_name(
                        f".{source.name}.trim-{token}{source.suffix}"
                    )
                    staged_candidates.append(staged_path)
                    if kind in {"media", "vocals"}:
                        self.ffmpeg.lossless_trim(
                            source,
                            staged_path,
                            resolved_start,
                            resolved_end,
                        )
                        self._validate_trimmed_media(
                            staged_path,
                            resolved_end - resolved_start,
                        )
                    elif kind == "lyrics":
                        self._shift_lyrics_file(
                            source,
                            staged_path,
                            resolved_start,
                            resolved_end,
                        )
                    staged[source] = staged_path

                self._install_staged_assets(staged, token)
            except Exception:
                for staged_path in staged_candidates:
                    staged_path.unlink(missing_ok=True)
                raise

            try:
                self.thumbnail_service.remove_thumbnail_for_media_file(media_file)
                self.thumbnail_service.ensure_thumbnail_for_media_file(media_file)
            except Exception:
                logger.exception(
                    "Failed to refresh thumbnail after trim media_id=%s path=%s",
                    media_item_id,
                    media_file,
                )

            media_item.updated_at = utc_now()
            db.commit()
            summary = {
                "media_id": media_item_id,
                "requested_start": requested_start,
                "requested_end": requested_end,
                "resolved_start": resolved_start,
                "resolved_end": resolved_end,
                "duration": round(resolved_end - resolved_start, 6),
                "trimmed_sidecars": [kind for kind, _ in assets if kind != "media"],
            }
            logger.info(
                "Media trim completed media_id=%s requested_start=%.6f requested_end=%.6f "
                "resolved_start=%.6f resolved_end=%.6f assets=%s",
                media_item_id,
                requested_start,
                requested_end,
                resolved_start,
                resolved_end,
                len(assets),
            )
            return summary
        finally:
            lock.release()

    def _get_media_item_and_file(
        self, db: Session, media_item_id: int
    ) -> tuple[MediaItem, Path]:
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise MediaTrimNotFoundError(f"Media item not found: {media_item_id}")
        media_file = self.queue_service._media_url_to_file(media_item.media_path)
        if media_item.missing or media_file is None or not media_file.is_file():
            raise MediaTrimNotFoundError("Media item file is missing")
        return media_item, media_file

    @staticmethod
    def _validate_time(value: object, field: str) -> float:
        if not isinstance(value, (int, float)):
            raise MediaTrimError(f"{field} must be a number")
        parsed = float(value)
        if not math.isfinite(parsed) or parsed < 0:
            raise MediaTrimError(f"{field} must be a finite non-negative number")
        return parsed

    @staticmethod
    def _resolve_bounds(
        start: float,
        end: float,
        duration: float,
        keyframes: list[float],
        *,
        has_video: bool,
    ) -> tuple[float, float]:
        if not has_video:
            return round(start, 6), round(end, 6)
        normalized = sorted(
            {
                0.0,
                duration,
                *(min(duration, max(0.0, float(value))) for value in keyframes),
            }
        )
        resolved_start = max(value for value in normalized if value <= start + 1e-6)
        resolved_end = min(value for value in normalized if value >= end - 1e-6)
        return round(resolved_start, 6), round(resolved_end, 6)

    @staticmethod
    def _lock_for(media_item_id: int) -> threading.Lock:
        with _TRIM_LOCKS_GUARD:
            return _TRIM_LOCKS.setdefault(media_item_id, threading.Lock())

    @staticmethod
    def _assert_no_conflicts(db: Session, media_item_id: int) -> None:
        playing = (
            db.query(QueueItem)
            .filter(
                QueueItem.media_id == media_item_id,
                QueueItem.status == QueueStatus.PLAYING.value,
            )
            .first()
        )
        if playing is not None:
            raise MediaTrimConflictError("Cannot trim a media item that is currently playing")
        active_task = (
            db.query(ProcessingTask)
            .filter(
                ProcessingTask.target_media_item_id == media_item_id,
                ProcessingTask.status.in_(_ACTIVE_TASK_STATUSES),
            )
            .first()
        )
        if active_task is not None:
            raise MediaTrimConflictError("Cannot trim a media item with active processing")

    def _collect_assets(
        self, media_item: MediaItem, media_file: Path
    ) -> list[tuple[str, Path]]:
        assets: list[tuple[str, Path]] = [("media", media_file)]
        for kind, media_url in (
            ("vocals", media_item.vocals_path),
            ("lyrics", media_item.lyrics_path),
        ):
            if not media_url:
                continue
            path = self.queue_service._media_url_to_file(media_url)
            if path is None or not path.is_file():
                raise MediaTrimNotFoundError(f"Attached {kind} file is missing")
            assets.append((kind, path))
        return assets

    def _validate_trimmed_media(self, path: Path, expected_duration: float) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise MediaTrimError(f"Trimmed output is empty: {path.name}")
        probe = self.ffmpeg.probe_media(path)
        actual_duration = float(probe["duration"])
        tolerance = max(1.0, expected_duration * 0.02)
        if actual_duration <= 0 or abs(actual_duration - expected_duration) > tolerance:
            raise MediaTrimError(
                f"Trimmed output duration is invalid: {actual_duration:.3f}s"
            )

    def _shift_lyrics_file(
        self,
        source: Path,
        output: Path,
        start: float,
        end: float,
    ) -> None:
        suffix = source.suffix.lower()
        if suffix == ".cdg":
            shutil.copy2(source, output)
            return

        text = source.read_text(encoding="utf-8")
        if suffix == ".lrc":
            shifted = self._shift_lrc(text, start, end)
        elif suffix == ".srt":
            shifted = self._shift_srt(text, start, end)
        elif suffix == ".json":
            shifted = self._shift_json(text, start, end)
        elif suffix == ".txt":
            shifted = text
        else:
            raise MediaTrimUnsupportedError(
                f"Unsupported timed lyrics format: {source.suffix}"
            )
        output.write_text(shifted, encoding="utf-8")

    @staticmethod
    def _shift_lrc(payload: str, start: float, end: float) -> str:
        parsed = pylrc.parse(payload)
        retained = []
        for line in parsed:
            line_time = float(line.time)
            if line_time < start or line_time > end:
                continue
            shifted_time = max(0.0, line_time - start)
            total_milliseconds = round(shifted_time * 1000)
            minutes, remainder = divmod(total_milliseconds, 60_000)
            seconds, milliseconds = divmod(remainder, 1000)
            retained.append(
                pylrc.classes.LyricLine(
                    f"[{minutes:02d}:{seconds:02d}.{milliseconds:03d}]",
                    line.text,
                )
            )
        timed = pylrc.classes.Lyrics(retained).toLRC().strip()
        metadata = [
            line
            for line in payload.splitlines()
            if line.strip().startswith("[")
            and ":" in line
            and not line.lstrip().startswith(tuple(f"[{digit}" for digit in "0123456789"))
        ]
        return "\n".join([*metadata, timed]).strip() + "\n"

    @staticmethod
    def _shift_srt(payload: str, start: float, end: float) -> str:
        window_start = timedelta(seconds=start)
        window_end = timedelta(seconds=end)
        shifted = []
        for subtitle in srt.parse(payload):
            if subtitle.end <= window_start or subtitle.start >= window_end:
                continue
            item = copy.copy(subtitle)
            item.start = max(subtitle.start, window_start) - window_start
            item.end = min(subtitle.end, window_end) - window_start
            if item.end <= item.start:
                continue
            shifted.append(item)
        return srt.compose(shifted, reindex=True)

    @classmethod
    def _shift_json(cls, payload: str, start: float, end: float) -> str:
        data = json.loads(payload)
        if isinstance(data, list):
            rows = data
            wrapper = None
        elif isinstance(data, dict):
            key = next(
                (
                    candidate
                    for candidate in ("segments", "cues", "items", "lines")
                    if isinstance(data.get(candidate), list)
                ),
                None,
            )
            if key is None:
                raise MediaTrimUnsupportedError("JSON lyrics do not contain timed rows")
            wrapper = copy.deepcopy(data)
            rows = data[key]
        else:
            raise MediaTrimUnsupportedError("JSON lyrics payload must be a list or object")

        shifted_rows = [
            shifted
            for row in rows
            if isinstance(row, dict)
            for shifted in [cls._shift_json_row(row, start, end)]
            if shifted is not None
        ]
        if wrapper is None:
            output: Any = shifted_rows
        else:
            wrapper[key] = shifted_rows
            output = wrapper
        return json.dumps(output, ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def _shift_json_row(
        cls, row: dict[str, Any], start: float, end: float
    ) -> dict[str, Any] | None:
        raw_start = row.get("start", row.get("time"))
        raw_end = row.get("end", raw_start)
        if not isinstance(raw_start, (int, float)) or not isinstance(raw_end, (int, float)):
            return None
        row_start = float(raw_start)
        row_end = float(raw_end)
        if row_end < start or row_start > end:
            return None

        shifted = copy.deepcopy(row)
        new_start = max(0.0, row_start - start)
        new_end = max(new_start, min(row_end, end) - start)
        if "start" in shifted:
            shifted["start"] = round(new_start, 3)
        else:
            shifted["time"] = round(new_start, 3)
        if "end" in shifted:
            shifted["end"] = round(new_end, 3)

        words = shifted.get("words")
        if isinstance(words, list):
            retained_words = []
            for word in words:
                if not isinstance(word, dict):
                    continue
                word_start = word.get("start")
                word_end = word.get("end")
                if not isinstance(word_start, (int, float)) or not isinstance(
                    word_end, (int, float)
                ):
                    continue
                if float(word_end) < start or float(word_start) > end:
                    continue
                shifted_word = copy.deepcopy(word)
                shifted_word["start"] = round(max(0.0, float(word_start) - start), 3)
                shifted_word["end"] = round(
                    max(
                        shifted_word["start"],
                        min(float(word_end), end) - start,
                    ),
                    3,
                )
                retained_words.append(shifted_word)
            shifted["words"] = retained_words
            if words and not retained_words:
                return None
            if retained_words:
                shifted["text"] = " ".join(
                    str(word.get("word", word.get("text", ""))).strip()
                    for word in retained_words
                    if str(word.get("word", word.get("text", ""))).strip()
                )
                shifted["start"] = retained_words[0]["start"]
                shifted["end"] = retained_words[-1]["end"]
        return shifted

    @staticmethod
    def _install_staged_assets(staged: dict[Path, Path], token: str) -> None:
        backups: dict[Path, Path] = {}
        installed: list[Path] = []
        try:
            for original in staged:
                backup = original.with_name(f".{original.name}.trim-backup-{token}")
                os.replace(original, backup)
                backups[original] = backup
            for original, staged_path in staged.items():
                os.replace(staged_path, original)
                installed.append(original)
        except Exception:
            logger.exception("Media trim installation failed; restoring original assets")
            for original in installed:
                original.unlink(missing_ok=True)
            for original, backup in backups.items():
                if backup.exists():
                    os.replace(backup, original)
            raise
        for backup in backups.values():
            backup.unlink(missing_ok=True)
