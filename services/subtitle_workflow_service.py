"""Subtitle export, preview, and replacement workflow."""
from __future__ import annotations

import copy
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import pysubs2
from fastapi import UploadFile
from sqlalchemy.orm import Session

from models import MediaItem, utc_now
from services.lyrics_service import LyricsService
from services.queue_service import QueueService

logger = logging.getLogger(__name__)

_ASS_KARAOKE_TAG_RE = re.compile(r"\{\\k(\d+)\}([^\{]*)")
_SRT_SEGMENT_MARKER_RE = re.compile(r"^\s*//wx:(\d+)//\s*", re.IGNORECASE)
_ALLOWED_UPLOAD_SUFFIXES = {".ass", ".ssa", ".srt"}
_ALLOWED_SOURCE_SUFFIXES = {".json"}


class SubtitleWorkflowError(ValueError):
    """Base workflow error."""


class SubtitleWorkflowNotFoundError(SubtitleWorkflowError):
    """Raised when a media item or file cannot be found."""


class SubtitleWorkflowConflictError(SubtitleWorkflowError):
    """Raised when the media item cannot accept subtitle edits."""


class SubtitleWorkflowService:
    """Convert between the app's JSON lyrics and subtitle editor files."""

    def __init__(self, queue_service: QueueService | None = None, lyrics_service: LyricsService | None = None):
        self.queue_service = queue_service or QueueService()
        self.lyrics_service = lyrics_service or LyricsService()

    def get_editable_media(self, db: Session, media_item_id: int) -> tuple[MediaItem, Path, Path]:
        """Return a media item and its current JSON lyrics file."""
        media_item = db.query(MediaItem).filter(MediaItem.id == media_item_id).first()
        if media_item is None:
            raise SubtitleWorkflowNotFoundError(f"Media item not found: {media_item_id}")
        if media_item.missing:
            raise SubtitleWorkflowNotFoundError("Media item file is missing")
        if not media_item.lyrics_path or not media_item.lyrics_path.strip():
            raise SubtitleWorkflowConflictError("Media item does not have synced JSON lyrics")

        lyrics_file = self.queue_service._media_url_to_file(media_item.lyrics_path)
        if lyrics_file is None or not lyrics_file.exists() or not lyrics_file.is_file():
            raise SubtitleWorkflowNotFoundError("JSON lyrics file not found")
        if lyrics_file.suffix.lower() not in _ALLOWED_SOURCE_SUFFIXES:
            raise SubtitleWorkflowConflictError("Subtitle editor requires synced JSON lyrics")

        media_file = self.queue_service._media_url_to_file(media_item.media_path)
        if media_file is None or not media_file.exists() or not media_file.is_file():
            raise SubtitleWorkflowNotFoundError("Media item file is missing")
        return media_item, media_file, lyrics_file

    def build_export_text(self, db: Session, media_item_id: int, export_format: str) -> tuple[str, str, dict[str, object]]:
        """Build a subtitle export for the requested editor format."""
        media_item, _media_file, _lyrics_file = self.get_editable_media(db, media_item_id)
        normalized_format = self._normalize_export_format(export_format)
        segments = self._load_json_segments(media_item)
        normalized_segments, warnings = self._normalize_segments(segments)
        if normalized_format == "ass":
            content = self._build_ass_export(normalized_segments)
            suffix = ".ass"
        else:
            content = self._build_srt_export(normalized_segments)
            suffix = ".srt"
        filename = f"{self._media_export_stem(media_item)}{suffix}"
        return content, filename, self._preview_summary(normalized_segments, warnings)

    def preview_upload(self, db: Session, media_item_id: int, upload_file: UploadFile) -> dict[str, object]:
        """Parse an edited subtitle file and return a JSON preview plus warnings."""
        media_item, _media_file, _lyrics_file = self.get_editable_media(db, media_item_id)
        parsed_segments, warnings, source_format = self._parse_uploaded_file(upload_file)
        normalized_segments, overlap_warnings = self._normalize_segments(parsed_segments)
        all_warnings = warnings + overlap_warnings
        return {
            "status": "ok",
            "media_id": media_item.id,
            "source_format": source_format,
            "preview": self._preview_summary(normalized_segments, all_warnings),
        }

    def replace_from_upload(self, db: Session, media_item_id: int, upload_file: UploadFile) -> dict[str, object]:
        """Replace the current JSON lyrics sidecar with imported edited subtitles."""
        media_item, _media_file, _lyrics_file = self.get_editable_media(db, media_item_id)
        parsed_segments, warnings, source_format = self._parse_uploaded_file(upload_file)
        normalized_segments, overlap_warnings = self._normalize_segments(parsed_segments)
        all_warnings = warnings + overlap_warnings
        payload = {"segments": normalized_segments}
        lyrics_text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.queue_service.store_lyrics_sidecar(
            media_item,
            lyrics_text,
            lyrics_format="json",
            storage="media",
        )
        media_item.updated_at = utc_now()
        db.commit()
        db.refresh(media_item)
        return {
            "status": "ok",
            "media_id": media_item.id,
            "lyrics_path": media_item.lyrics_path,
            "source_format": source_format,
            "warnings": all_warnings,
            "preview": self._preview_summary(normalized_segments, all_warnings),
        }

    def _load_json_segments(self, media_item: MediaItem) -> list[dict[str, Any]]:
        payload = self.lyrics_service.load_lyrics_payload_from_media_url(media_item.lyrics_path or "")
        cues = payload.get("cues", [])
        segments: list[dict[str, Any]] = []
        for cue in cues:
            if not isinstance(cue, dict):
                continue
            start = cue.get("time")
            if not isinstance(start, (int, float)):
                continue
            end = cue.get("end", start)
            if not isinstance(end, (int, float)):
                end = start
            text = str(cue.get("text", "")).strip()
            words = self._normalize_words(cue.get("words"))
            if not text and words:
                text = " ".join(word["word"] for word in words)
            if not text:
                continue
            segment: dict[str, Any] = {
                "start": round(float(start), 3),
                "end": round(max(float(start), float(end)), 3),
                "text": text,
                "words": words or [{"word": text, "start": round(float(start), 3), "end": round(max(float(start), float(end)), 3)}],
            }
            segments.append(segment)
        segments.sort(key=lambda row: float(row["start"]))
        return segments

    def _parse_uploaded_file(self, upload_file: UploadFile) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
        filename = Path(upload_file.filename or "").name
        suffix = Path(filename).suffix.lower()
        if suffix not in _ALLOWED_UPLOAD_SUFFIXES:
            raise SubtitleWorkflowConflictError("Supported uploads are .ass, .ssa, and .srt")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)
            try:
                upload_file.file.seek(0)
            except Exception:
                pass
            try:
                handle.write(upload_file.file.read())
            finally:
                handle.flush()

        try:
            subs = pysubs2.load(str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

        if suffix in {".ass", ".ssa"}:
            return self._parse_ass_subtitles(subs), [], "ass"
        return self._parse_srt_subtitles(subs), [], "srt"

    @staticmethod
    def _parse_ass_subtitles(subs: pysubs2.SSAFile) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []
        for line in sorted(subs, key=lambda event: (event.start, event.end)):
            text = str(line.text or "").strip()
            if not text:
                continue
            matches = _ASS_KARAOKE_TAG_RE.findall(text)
            start = round(float(line.start) / 1000.0, 3)
            end = round(float(line.end) / 1000.0, 3)
            if not matches:
                plain_text = SubtitleWorkflowService._strip_ass_tags(text)
                if not plain_text:
                    continue
                segments.append(
                    {
                        "start": start,
                        "end": end,
                        "text": plain_text,
                        "words": [
                            {
                                "word": plain_text,
                                "start": start,
                                "end": end,
                            }
                        ],
                    }
                )
                continue

            words: list[dict[str, Any]] = []
            current = start
            for duration_cs, word_text in matches:
                duration = max(0.0, float(duration_cs) / 100.0)
                word_start = round(current, 3)
                word_end = round(current + duration, 3)
                clean_word = SubtitleWorkflowService._clean_subtitle_word(word_text)
                if clean_word:
                    words.append({"word": clean_word, "start": word_start, "end": word_end})
                current = current + duration
            if not words:
                continue
            if words[-1]["end"] < end:
                words[-1]["end"] = end
            segments.append(
                {
                    "start": start,
                    "end": end,
                    "text": " ".join(word["word"] for word in words),
                    "words": words,
                }
            )
        return segments

    @staticmethod
    def _parse_srt_subtitles(subs: pysubs2.SSAFile) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []
        current_segment: dict[str, Any] | None = None
        for line in sorted(subs, key=lambda event: (event.start, event.end)):
            text = str(line.text or "").strip()
            if not text or text.startswith("//wx:meta//"):
                continue

            marker_match = _SRT_SEGMENT_MARKER_RE.match(text)
            clean_text = _SRT_SEGMENT_MARKER_RE.sub("", text).strip()
            if not clean_text:
                continue
            word = {
                "word": clean_text,
                "start": round(float(line.start) / 1000.0, 3),
                "end": round(float(line.end) / 1000.0, 3),
            }

            if marker_match or current_segment is None:
                if current_segment is not None:
                    segments.append(current_segment)
                current_segment = {
                    "start": word["start"],
                    "end": word["end"],
                    "text": clean_text,
                    "words": [word],
                }
                continue

            current_segment["words"].append(word)
            current_segment["end"] = max(float(current_segment["end"]), word["end"])
            current_segment["text"] = " ".join(str(item["word"]) for item in current_segment["words"])

        if current_segment is not None:
            segments.append(current_segment)
        return segments

    @staticmethod
    def _normalize_export_format(export_format: str) -> str:
        normalized = str(export_format or "").strip().lower()
        if normalized not in {"ass", "srt"}:
            raise SubtitleWorkflowConflictError(f"Unsupported subtitle export format: {export_format}")
        return normalized

    @staticmethod
    def _normalize_words(words: object) -> list[dict[str, Any]]:
        if not isinstance(words, list):
            return []
        normalized: list[dict[str, Any]] = []
        for row in words:
            if not isinstance(row, dict):
                continue
            word = str(row.get("word", "")).strip()
            start = row.get("start")
            end = row.get("end")
            if not word or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                continue
            start_value = round(float(start), 3)
            end_value = round(float(end), 3)
            if end_value < start_value:
                continue
            normalized.append({"word": word, "start": start_value, "end": end_value})
        normalized.sort(key=lambda row: float(row["start"]))
        return normalized

    @staticmethod
    def _normalize_segments(segments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        normalized = [copy.deepcopy(segment) for segment in segments]
        normalized.sort(key=lambda row: float(row.get("start", 0.0)))
        warnings: list[dict[str, Any]] = []

        for index, segment in enumerate(normalized):
            segment["start"] = round(max(0.0, float(segment.get("start", 0.0))), 3)
            segment["end"] = round(max(segment["start"], float(segment.get("end", segment["start"]))), 3)
            words = SubtitleWorkflowService._normalize_words(segment.get("words"))
            if not words:
                text = str(segment.get("text", "")).strip()
                if text:
                    words = [{"word": text, "start": segment["start"], "end": segment["end"]}]
            segment["words"] = words
            segment["text"] = str(segment.get("text", "")).strip() or " ".join(word["word"] for word in words)

            if index + 1 >= len(normalized):
                continue
            next_segment = normalized[index + 1]
            next_start = float(next_segment.get("start", 0.0))
            if segment["end"] > next_start:
                warnings.append(
                    {
                        "type": "overlap",
                        "segment_index": index,
                        "current_text": segment["text"],
                        "next_text": str(next_segment.get("text", "")).strip(),
                        "current_end": segment["end"],
                        "next_start": round(next_start, 3),
                    }
                )
                segment["end"] = round(next_start, 3)
                for word in segment["words"]:
                    if float(word["end"]) > segment["end"]:
                        word["end"] = segment["end"]
                    if float(word["start"]) > segment["end"]:
                        word["start"] = segment["end"]
        return normalized, warnings

    @staticmethod
    def _preview_summary(segments: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> dict[str, object]:
        word_count = sum(len(segment.get("words", [])) for segment in segments)
        return {
            "segment_count": len(segments),
            "word_count": word_count,
            "warning_count": len(warnings),
            "warnings": warnings,
        }

    @staticmethod
    def _build_ass_export(segments: list[dict[str, Any]]) -> str:
        ass = pysubs2.SSAFile()
        for segment in segments:
            event = pysubs2.SSAEvent()
            event.start = pysubs2.make_time(s=float(segment["start"]))
            event.end = pysubs2.make_time(s=float(segment["end"]))
            event.text = SubtitleWorkflowService._build_ass_line(segment)
            ass.append(event)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ass") as handle:
            temp_path = Path(handle.name)
        try:
            ass.save(str(temp_path))
            return temp_path.read_text(encoding="utf-8")
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _build_ass_line(segment: dict[str, Any]) -> str:
        words = segment.get("words") or []
        if not words:
            return SubtitleWorkflowService._escape_ass_text(str(segment.get("text", "")).strip())

        line_parts: list[str] = []
        for index, word in enumerate(words):
            word_text = SubtitleWorkflowService._escape_ass_text(str(word.get("word", "")).strip())
            if not word_text:
                continue
            if index + 1 < len(words):
                next_start = float(words[index + 1]["start"])
            else:
                next_start = float(segment["end"])
            duration = max(0.0, next_start - float(word["start"]))
            line_parts.append(f"{{\\k{int(duration * 100)}}}{word_text} ")
        return "".join(line_parts).rstrip()

    @staticmethod
    def _build_srt_export(segments: list[dict[str, Any]]) -> str:
        subs = pysubs2.SSAFile()
        meta_warning = pysubs2.SSAEvent()
        meta_warning.start = pysubs2.make_time(s=0)
        meta_warning.end = pysubs2.make_time(s=0)
        meta_warning.text = "//wx:meta//Warning:"
        subs.append(meta_warning)

        meta_hint = pysubs2.SSAEvent()
        meta_hint.start = pysubs2.make_time(s=0)
        meta_hint.end = pysubs2.make_time(s=0)
        meta_hint.text = "//wx:meta//Do not remove //wx:// tags."
        subs.append(meta_hint)

        for index, segment in enumerate(segments):
            words = segment.get("words") or []
            if not words:
                event = pysubs2.SSAEvent()
                event.start = pysubs2.make_time(s=float(segment["start"]))
                event.end = pysubs2.make_time(s=float(segment["end"]))
                event.text = f"//wx:{index * 10}//{str(segment.get('text', '')).strip()}"
                subs.append(event)
                continue

            for word_index, word in enumerate(words):
                event = pysubs2.SSAEvent()
                event.start = pysubs2.make_time(s=float(word["start"]))
                event.end = pysubs2.make_time(s=float(word["end"]))
                prefix = f"//wx:{index * 10}//" if word_index == 0 else ""
                event.text = f"{prefix}{str(word.get('word', '')).strip()}"
                subs.append(event)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as handle:
            temp_path = Path(handle.name)
        try:
            subs.save(str(temp_path))
            return temp_path.read_text(encoding="utf-8")
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _clean_subtitle_word(text: str) -> str:
        cleaned = str(text or "").replace("\n", " ").replace("\r", " ").strip()
        return cleaned

    @staticmethod
    def _strip_ass_tags(text: str) -> str:
        return re.sub(r"\{[^}]*\}", "", text).strip()

    @staticmethod
    def _escape_ass_text(text: str) -> str:
        return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

    @staticmethod
    def _media_export_stem(media_item: MediaItem) -> str:
        media_file = Path(media_item.media_path).name if media_item.media_path else ""
        if media_file:
            return Path(media_file).stem
        return media_item.file_stem or media_item.title or f"media-{media_item.id}"


subtitle_workflow_service = SubtitleWorkflowService()

