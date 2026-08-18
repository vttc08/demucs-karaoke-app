"""Synced JSON lyric split/merge editor service."""
from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from demucs_svc.lyrics_line_processor import process_lyric_lines
from demucs_svc.whisperx_pipeline import (
    ParsedLyricSegment,
    _join_display_tokens,
    _rebuild_segments,
)
from models import MediaItem, utc_now
from services.lyrics_service import LyricsService
from services.queue_service import QueueService
from services.subtitle_workflow_service import (
    SubtitleWorkflowConflictError,
    subtitle_workflow_service,
)

logger = logging.getLogger(__name__)

_SEGMENT_MARKER_RE = re.compile(r"^\s*//wx:(\d+)//\s*", re.IGNORECASE)


@dataclass(frozen=True)
class SubtitleEditorPayload:
    media_id: int
    title: str
    artist: str | None
    lyrics_path: str
    source_format: str
    segments: list[dict[str, Any]]


class SubtitleEditorService:
    """Load, edit, rewrap, and persist synced JSON lyrics."""

    def __init__(self, queue_service: QueueService | None = None, lyrics_service: LyricsService | None = None):
        self.queue_service = queue_service or QueueService()
        self.lyrics_service = lyrics_service or LyricsService()

    def _get_editable_media(self, db: Session, media_item_id: int) -> tuple[MediaItem, Path]:
        media_item, _media_file, lyrics_file = subtitle_workflow_service.get_editable_media(db, media_item_id)
        if lyrics_file.suffix.lower() != ".json":
            raise SubtitleWorkflowConflictError("Subtitle editor requires synced JSON lyrics")
        return media_item, lyrics_file

    def load_editor_payload(self, db: Session, media_item_id: int) -> SubtitleEditorPayload:
        media_item, _lyrics_file = self._get_editable_media(db, media_item_id)
        segments = self._load_segments(media_item)
        return SubtitleEditorPayload(
            media_id=media_item.id,
            title=media_item.title,
            artist=media_item.artist,
            lyrics_path=media_item.lyrics_path or "",
            source_format="json",
            segments=segments,
        )

    def save_segments(self, db: Session, media_item_id: int, segments: list[dict[str, Any]]) -> SubtitleEditorPayload:
        media_item, _lyrics_file = self._get_editable_media(db, media_item_id)
        normalized_segments = self._compact_segments(segments)
        lyrics_text = json.dumps({"segments": normalized_segments}, ensure_ascii=False, indent=2)
        self.queue_service.store_lyrics_sidecar(
            media_item,
            lyrics_text,
            lyrics_format="json",
            storage="media",
        )
        media_item.updated_at = utc_now()
        db.commit()
        db.refresh(media_item)
        return SubtitleEditorPayload(
            media_id=media_item.id,
            title=media_item.title,
            artist=media_item.artist,
            lyrics_path=media_item.lyrics_path or "",
            source_format="json",
            segments=normalized_segments,
        )

    def split_segment(self, segments: list[dict[str, Any]], index: int, word_index: int) -> list[dict[str, Any]]:
        normalized = self._normalize_segments(segments)
        if index < 0 or index >= len(normalized):
            raise SubtitleWorkflowConflictError("Segment index out of range")
        segment = normalized[index]
        words = list(segment.get("words") or [])
        if word_index <= 0 or word_index >= len(words):
            raise SubtitleWorkflowConflictError("Word index out of range")

        first_words = copy.deepcopy(words[:word_index])
        second_words = copy.deepcopy(words[word_index:])
        if not first_words or not second_words:
            raise SubtitleWorkflowConflictError("Cannot split an empty segment")

        first_segment = self._make_segment_from_words(first_words)
        second_segment = self._make_segment_from_words(second_words)
        return normalized[:index] + [first_segment, second_segment] + normalized[index + 1 :]

    def merge_segment(self, segments: list[dict[str, Any]], index: int) -> list[dict[str, Any]]:
        normalized = self._normalize_segments(segments)
        if index < 0 or index >= len(normalized) - 1:
            raise SubtitleWorkflowConflictError("Merge index out of range")

        left = normalized[index]
        right = normalized[index + 1]
        merged_words = copy.deepcopy(list(left.get("words") or []) + list(right.get("words") or []))
        if not merged_words:
            raise SubtitleWorkflowConflictError("Cannot merge empty segments")
        return normalized[:index] + [self._make_segment_from_words(merged_words)] + normalized[index + 2 :]

    def process_segments(
        self,
        segments: list[dict[str, Any]],
        *,
        max_line_length: int,
        max_line_length_cjk: int,
    ) -> list[dict[str, Any]]:
        normalized = self._compact_segments(segments)
        return self._rewrap_segments(normalized, max_line_length=max_line_length, max_line_length_cjk=max_line_length_cjk)

    def process_saved_segments(
        self,
        db: Session,
        media_item_id: int,
        *,
        max_line_length: int,
        max_line_length_cjk: int,
    ) -> list[dict[str, Any]]:
        media_item, _lyrics_file = self._get_editable_media(db, media_item_id)
        segments = self._compact_segments(self._load_segments(media_item))
        return self._rewrap_segments(segments, max_line_length=max_line_length, max_line_length_cjk=max_line_length_cjk)

    def _rewrap_segments(
        self,
        segments: list[dict[str, Any]],
        *,
        max_line_length: int,
        max_line_length_cjk: int,
    ) -> list[dict[str, Any]]:
        if not segments:
            return []

        processed_lines = process_lyric_lines(
            [str(segment.get("text", "")).strip() for segment in segments if str(segment.get("text", "")).strip()],
            max_line_length=max_line_length,
            max_line_length_cjk=max_line_length_cjk,
        )
        if not processed_lines:
            return []

        processed_segments = [ParsedLyricSegment(text=line, start=0.0, end=0.0) for line in processed_lines]
        aligned_words = [word for segment in segments for word in list(segment.get("words") or [])]
        if not aligned_words:
            return self._normalize_segments(
                [
                    {
                        "start": 0.0,
                        "end": 0.0,
                        "text": line,
                        "words": [{"word": line, "start": 0.0, "end": 0.0}],
                    }
                    for line in processed_lines
                ]
            )
        rebuilt = _rebuild_segments(processed_segments, aligned_words)
        if not rebuilt:
            return []
        return self._compact_segments(rebuilt)

    def _load_segments(self, media_item: MediaItem) -> list[dict[str, Any]]:
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
            segments.append(
                {
                    "start": round(float(start), 3),
                    "end": round(max(float(start), float(end)), 3),
                    "text": text,
                    "words": words or [
                        {
                            "word": text,
                            "start": round(float(start), 3),
                            "end": round(max(float(start), float(end)), 3),
                        }
                    ],
                }
            )
        return self._compact_segments(segments)

    @classmethod
    def _compact_segments(cls, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compacted: list[dict[str, Any]] = []
        for segment in cls._normalize_segments(segments):
            text = str(segment.get("text", "")).strip()
            words = list(segment.get("words") or [])
            if not text and not words:
                continue
            compacted.append(segment)
        return compacted

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

    @classmethod
    def _normalize_segments(cls, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = [copy.deepcopy(segment) for segment in segments]
        normalized.sort(key=lambda row: float(row.get("start", 0.0)))
        for index, segment in enumerate(normalized):
            segment["start"] = round(max(0.0, float(segment.get("start", 0.0))), 3)
            segment["end"] = round(max(segment["start"], float(segment.get("end", segment["start"]))), 3)
            words = cls._normalize_words(segment.get("words"))
            if not words:
                text = str(segment.get("text", "")).strip()
                if text:
                    words = [{"word": text, "start": segment["start"], "end": segment["end"]}]
            segment["words"] = words
            segment["text"] = str(segment.get("text", "")).strip() or " ".join(word["word"] for word in words)
            if index + 1 < len(normalized):
                next_segment = normalized[index + 1]
                next_start = float(next_segment.get("start", 0.0))
                if segment["end"] > next_start:
                    segment["end"] = round(next_start, 3)
                    if segment["end"] < segment["start"]:
                        segment["end"] = segment["start"]
                    if segment["words"]:
                        segment["words"][-1]["end"] = segment["end"]
        return normalized

    @staticmethod
    def _make_segment_from_words(words: list[dict[str, Any]]) -> dict[str, Any]:
        current_words = [word for word in words if str(word.get("word", "")).strip()]
        if not current_words:
            return {"start": 0.0, "end": 0.0, "text": "", "words": []}
        return {
            "start": float(current_words[0].get("start", 0.0) or 0.0),
            "end": float(current_words[-1].get("end", 0.0) or 0.0),
            "text": _join_display_tokens(str(word.get("word", "")) for word in current_words),
            "words": current_words,
        }


subtitle_editor_service = SubtitleEditorService()
